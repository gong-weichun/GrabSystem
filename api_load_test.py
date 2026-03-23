"""
Melon Ticket 抢票测试 v8 - 自动适配 + 智能选座
只需配置 PROD_ID + SCHEDULE_NO + Cookie，其余参数全部自动获取
支持指定席(DR0002)和自由席(DR0003)两种模式

完整链路: getMemberKey -> onestop.htm -> prodKey -> informProdSch -> tickettype
         -> seatStateInfo -> delivery -> pricelimit -> getNoRsrvSeq -> save
"""
import io
import json
import os
import re
import time
import urllib.parse
from collections import defaultdict
from html.parser import HTMLParser
from curl_cffi.requests import Session

# ==========================================
# 配置区 - 只需修改以下内容
# ==========================================
PROD_ID = "212638"            # 产品ID (换产品只改这里)
SCHEDULE_NO = "100001"        # 场次编号
POC_CODE = "SC0002"           # 渠道 (SC0002=Global Web)
SELL_TYPE_CODE = "ST0001"     # 售票类型
VOLUME = 1                    # 购买数量

# 可选: 指定想要的区域关键词 (留空则自动选最多余票的区域)
# 例如: "C3", "D1", "Floor 2", "Floor 1,Sec D1" 等
PREFERRED_SECTION = "C3"

USER_EMAIL = "877605465@qq.com"
USER_PHONE = "15864230665"

PROXIES = {"https": "http://127.0.0.1:7897", "http": "http://127.0.0.1:7897"}
IMPERSONATE = "chrome110"

COOKIE = '_fwb=150r4Q5wK0yq1b5RDTDn7cq.1753524124532; PCID=17535241246108694755228; TKT_POC_ID=WP19; i18next=EN; NetFunnel_ID=WP15; keyCookie_T=1007828360; MAC_T="fH2/f7duFWy4ZLwt+GBVb/qbPNH3H7+LC7nraNHcilqEPtcLCpXleGRwU5ObZFrXYweyKHECGTFi5X9R91mvuw=="; JSESSIONID=49BF3A6B727333ADDEF64EBFA16206DE; wcs_bt=s_322bdbd6fd48:1774188401'


# ==========================================
# 工具函数
# ==========================================
def extract_jsonp(text):
    """从 JSONP 或纯 JSON 响应中提取 JSON 对象"""
    match = re.search(r'\((\{.*\})\)', text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    text = text.strip()
    if text.startswith('{'):
        return json.loads(text)
    return None


def normalize_captcha_text(text):
    """Keep only alphanumerics so OCR punctuation does not poison verification."""
    if not text:
        return ""
    return "".join(ch for ch in text.upper().strip() if ch.isalnum())


def build_captcha_ocr_candidates(captcha_bytes, ocr):
    """
    Melon captcha payload is an RGBA PNG where the useful strokes live in alpha.
    Recover visible grayscale variants and ask OCR for multiple guesses.
    """
    if not ocr:
        return []

    from PIL import Image, ImageOps

    image = Image.open(io.BytesIO(captcha_bytes)).convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        left, top, right, bottom = bbox
        alpha = alpha.crop((max(0, left - 2), max(0, top - 2), min(image.width, right + 2), min(image.height, bottom + 2)))

    variants = []

    def add_variant(img, name):
        resized = img.resize((img.width * 3, img.height * 3), Image.Resampling.LANCZOS)
        variants.append((name, resized))

    add_variant(alpha, "alpha")
    add_variant(ImageOps.autocontrast(alpha), "alpha_autocontrast")
    add_variant(ImageOps.invert(alpha), "alpha_invert")

    for threshold in (72, 96, 128, 160, 192):
        bw = alpha.point(lambda p, t=threshold: 255 if p >= t else 0, mode="L")
        add_variant(bw, f"alpha_bw_{threshold}")
        add_variant(ImageOps.invert(bw), f"alpha_bw_inv_{threshold}")

    guesses = []
    seen = set()
    for name, variant in variants:
        buffer = io.BytesIO()
        variant.save(buffer, format="PNG")
        guess = normalize_captcha_text(ocr.classification(buffer.getvalue()))
        if guess and guess not in seen:
            guesses.append((name, guess))
            seen.add(guess)
    return guesses


def verify_captcha_guess(session, headers, prod_id, schedule_no, poc_code, sell_type_code, user_capt, chkcapt_val):
    capt_check_data = (
        f"userCaptStr={user_capt}"
        f"&chkcapt={chkcapt_val}"
        f"&prodId={prod_id}"
        f"&scheduleNo={schedule_no}"
        f"&pocCode={poc_code}"
        f"&sellTypeCode={sell_type_code}"
    )
    response = session.post(
        "https://tkglobal.melon.com/reservation/ajax/checkCaptcha.json",
        data=capt_check_data,
        headers=headers,
        timeout=10,
    )
    return extract_jsonp(response.text)


def get_selected_card_meta(delivery_data, preferred_card_code="FOREIGN_CHINABANK"):
    """Match the selected payment card to the metadata stepDelvy serializes into the final form."""
    card_list = delivery_data.get("cardBpList", []) if isinstance(delivery_data, dict) else []
    selected = None
    for card in card_list:
        if card.get("cardBpId") == preferred_card_code:
            selected = card
            break
    if not selected and card_list:
        selected = card_list[0]
    return {
        "card_code": (selected or {}).get("cardBpId", preferred_card_code),
        "card_name": (selected or {}).get("cardBpName", "UnionPay"),
        "authe_type_code": (selected or {}).get("autheTypeCode", ""),
        "card_quota": str((selected or {}).get("cardQuota", "12") or "12"),
        "quota": "00",
        # cardBpId/cardMid in stepDelvy come from parent hidden discount-card state, not payment card selection.
        "card_bp_id": "",
        "card_mid": "",
    }


def iter_designated_seats(seat_data):
    """Flatten the stepBlock seatMapList payload into clickable seat records."""
    if isinstance(seat_data, dict):
        st_list = seat_data.get("st")
        if isinstance(st_list, list):
            for section in st_list:
                for seat in iter_designated_seats(section):
                    yield seat
            return

        ss_list = seat_data.get("ss")
        if isinstance(ss_list, list):
            for seat in ss_list:
                if isinstance(seat, dict):
                    yield seat
            return

        for value in seat_data.values():
            for seat in iter_designated_seats(value):
                yield seat
    elif isinstance(seat_data, list):
        for item in seat_data:
            for seat in iter_designated_seats(item):
                yield seat


def fetch_designated_seat(session, headers_get, headers_post, prod_id, schedule_no, poc_code, block_id, preferred_grade_no):
    """
    Mirror stepBlock: initialize the block view, then fetch live seats from seatMapList.
    tickettype seatList is only a coarse hint and can be stale by save-time.
    """
    step_block_url = "https://tkglobal.melon.com/reservation/popup/stepBlock.htm?langCd=EN"
    session.get(step_block_url, headers={**headers_get, "Referer": "https://tkglobal.melon.com/reservation/popup/onestop.htm"}, timeout=10)

    block_headers_get = {**headers_get, "Referer": step_block_url}
    block_headers_post = {**headers_post, "Referer": step_block_url}

    area_map_response = session.post(
        "https://tkglobal.melon.com/tktapi/glb/product/getAreaMap.json?v=1&callback=getBlockGradeSeatMapCallBack",
        data=f"prodId={prod_id}&scheduleNo={schedule_no}&pocCode={poc_code}",
        headers=block_headers_post,
        timeout=10,
    )
    area_map = extract_jsonp(area_map_response.text) or {}
    block_summary_response = session.post(
        "https://tkglobal.melon.com/tktapi/product/block/summary.json?v=1&callback=getBlockSummaryCountCallBack",
        data=f"prodId={prod_id}&pocCode={poc_code}&scheduleNo={schedule_no}&seatGradeNo=",
        headers=block_headers_post,
        timeout=10,
    )
    block_summary = extract_jsonp(block_summary_response.text) or {}
    block_grade_summary = {}
    if preferred_grade_no:
        block_grade_summary_response = session.post(
            "https://tkglobal.melon.com/tktapi/product/block/summary.json?v=1&callback=getBlockSummaryCallBack",
            data=f"prodId={prod_id}&pocCode={poc_code}&scheduleNo={schedule_no}&seatGradeNo={preferred_grade_no}",
            headers=block_headers_post,
            timeout=10,
        )
        block_grade_summary = extract_jsonp(block_grade_summary_response.text) or {}

    response = session.get(
        "https://tkglobal.melon.com/tktapi/product/seat/seatMapList.json"
        f"?callback=getSeatListCallBack&v=1&prodId={prod_id}&scheduleNo={schedule_no}&blockId={block_id}&pocCode={poc_code}&corpCodeNo=",
        headers=block_headers_get,
        timeout=10,
    )
    result = extract_jsonp(response.text)
    if not result or str(result.get("code", "0000")) not in ("0000", ""):
        return None, result, response.text[:300], {}

    block_context = {}
    seat_data_root = area_map.get("seatData", {}) if isinstance(area_map, dict) else {}
    seat_name_tokens = seat_data_root.get("snt", {}) if isinstance(seat_data_root, dict) else {}
    st_list = seat_data_root.get("st", []) if isinstance(seat_data_root, dict) else []
    zb_list = seat_data_root.get("da", {}).get("zb", []) if isinstance(seat_data_root.get("da", {}), dict) else []
    if isinstance(st_list, list) and isinstance(zb_list, list):
        for section, zone in zip(st_list, zb_list):
            if not isinstance(section, dict) or not isinstance(zone, dict):
                continue
            if str(section.get("sbid") or "") != str(block_id):
                continue
            snt = zone.get("snt", {}) if isinstance(zone.get("snt", {}), dict) else {}
            floor_no = str(snt.get("f") or "")
            area_no = str(snt.get("a") or "")
            block_context = {
                "sntv": ",".join(part for part in (floor_no, area_no) if part),
                "blockTypeCode": "",
                "floorNo": floor_no,
                "floorName": str((seat_name_tokens.get("f") or {}).get("name") or ""),
                "areaNo": area_no,
                "areaName": str((seat_name_tokens.get("a") or {}).get("name") or ""),
            }
            break
    for source in (block_grade_summary, block_summary):
        summary_list = source.get("summary", []) if isinstance(source, dict) else []
        if not isinstance(summary_list, list):
            continue
        for item in summary_list:
            if not isinstance(item, dict):
                continue
            candidate_block_id = (
                item.get("blockId")
                or item.get("blkId")
                or item.get("zoneId")
                or item.get("seatBlockId")
            )
            if str(candidate_block_id or "") != str(block_id):
                continue
            block_context = {
                "sntv": block_context.get("sntv") or str(item.get("sntv") or ""),
                "blockTypeCode": block_context.get("blockTypeCode") or str(item.get("blockTypeCode") or ""),
                "floorNo": block_context.get("floorNo") or str(item.get("floorNo") or ""),
                "floorName": block_context.get("floorName") or str(item.get("floorName") or ""),
                "areaNo": block_context.get("areaNo") or str(item.get("areaNo") or ""),
                "areaName": block_context.get("areaName") or str(item.get("areaName") or ""),
            }
            break
        if block_context:
            break

    live_seats = []
    for seat in iter_designated_seats(result.get("seatData", {})):
        sid = str(seat.get("sid") or "")
        gd = str(seat.get("gd") or "")
        if not sid:
            continue
        live_seats.append(
            {
                "seatId": sid,
                "seatGradeNo": gd or preferred_grade_no,
                "seatTypeCode": str(seat.get("st") or seat.get("seatTypeCode") or ""),
                "clipSeatId": str(seat.get("csid") or "0"),
                "seatName": str(
                    seat.get("krtit")
                    or seat.get("tit")
                    or seat.get("title")
                    or seat.get("snm")
                    or seat.get("sn")
                    or sid
                ),
                "seatGradeName": str(seat.get("gn") or ""),
            }
        )

    if not live_seats:
        return None, result, "no_live_seats", block_context

    if preferred_grade_no:
        filtered = [seat for seat in live_seats if seat["seatGradeNo"] == preferred_grade_no]
        if filtered:
            live_seats = filtered

    return live_seats[0], result, "", block_context


def submit_designated_prodlimit(session, headers, base_form_body, seat_id, clip_seat_id, chkcapt_val):
    """
    stepBlock locks designated seats via prodlimit before stepTicket/stepDelvy.
    Without this handshake, save.json eventually fails with stale-seat style errors.
    """
    body = (
        f"{base_form_body}"
        f"&seatId={seat_id}"
        f"&clipSeatId={clip_seat_id}"
        f"&chkcapt={chkcapt_val}"
    )
    response = session.post(
        "https://tkglobal.melon.com/tktapi/glb/reservation/prodlimit.json?v=1&callback=prodlimitHandler",
        data=body,
        headers=headers,
        timeout=15,
    )
    return extract_jsonp(response.text), response


def parse_form_body(body):
    return urllib.parse.parse_qsl(body, keep_blank_values=True)


def encode_form_pairs(pairs):
    return urllib.parse.urlencode(
        [(name, "" if value is None else str(value)) for name, value in pairs],
        doseq=True,
    )


def upsert_form_field(pairs, name, value):
    value = "" if value is None else str(value)
    replaced = False
    updated = []
    for key, current in pairs:
        if key == name:
            if not replaced:
                updated.append((key, value))
                replaced = True
        else:
            updated.append((key, current))
    if not replaced:
        updated.append((name, value))
    return updated


def build_post_lock_form_body(base_form_body, encrypted_seat_ids="", interlock_type_code="", interlock_tid="", seat_type_code="", extra_fields=None):
    pairs = parse_form_body(base_form_body)
    if seat_type_code:
        pairs = upsert_form_field(pairs, "seatTypeCode", seat_type_code)
    if encrypted_seat_ids:
        pairs = upsert_form_field(pairs, "encryptedSeatIds", encrypted_seat_ids)
    if interlock_type_code:
        pairs = upsert_form_field(pairs, "interlockTypeCode", interlock_type_code)
    if interlock_tid:
        pairs = upsert_form_field(pairs, "interlockTid", interlock_tid)
    for name, value in (extra_fields or {}).items():
        if value is None or value == "":
            continue
        pairs = upsert_form_field(pairs, name, value)
    return encode_form_pairs(pairs)


class InputFieldParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "input":
            return
        attr_map = {key.lower(): value for key, value in attrs}
        name = attr_map.get("name") or attr_map.get("id")
        if not name:
            return
        self.fields.append(
            {
                "name": name,
                "id": attr_map.get("id", ""),
                "type": attr_map.get("type", ""),
                "value": attr_map.get("value", ""),
            }
        )


def extract_input_fields_from_html(html_text):
    parser = InputFieldParser()
    parser.feed(html_text or "")
    return parser.fields


def get_html_input_value(html_text, *field_names):
    wanted = {str(name) for name in field_names if name}
    if not wanted:
        return ""
    for field in extract_input_fields_from_html(html_text):
        if field["name"] in wanted or field["id"] in wanted:
            return str(field.get("value", "") or "")
    return ""


def extract_payment_targets_from_html(html_text):
    targets = []
    if not html_text:
        return targets

    patterns = [
        r'action=["\']([^"\']+)["\']',
        r'src=["\']([^"\']+)["\']',
        r'location\.href\s*=\s*["\']([^"\']+)["\']',
        r'location\.replace\(["\']([^"\']+)["\']\)',
        r'open\(["\']([^"\']+)["\']',
    ]
    seen = set()
    for pattern in patterns:
        for match in re.findall(pattern, html_text, re.IGNORECASE):
            url = str(match or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            targets.append(url)
    return targets


def extract_seat_type_code(tickettype_data, preferred_seat_id=""):
    seat_list = tickettype_data.get("seatList", []) if isinstance(tickettype_data, dict) else []
    if not isinstance(seat_list, list):
        return ""

    preferred_seat_id = str(preferred_seat_id or "")
    for item in seat_list:
        if not isinstance(item, dict):
            continue
        if preferred_seat_id and str(item.get("seatId") or "") != preferred_seat_id:
            continue
        seat_type_code = str(item.get("seatTypeCode") or "")
        if seat_type_code:
            return seat_type_code

    for item in seat_list:
        if not isinstance(item, dict):
            continue
        seat_type_code = str(item.get("seatTypeCode") or "")
        if seat_type_code:
            return seat_type_code

    return ""


def post_step_ticket_page(session, headers, prod_id, schedule_no, flplan_type_code, seat_type_code,
                          seat_ids, encrypted_seat_ids="", interlock_type_code="", interlock_tid=""):
    pairs = [
        ("prodId", prod_id),
        ("scheduleNo", schedule_no),
        ("flplanTypeCode", flplan_type_code),
        ("seatTypeCode", seat_type_code),
    ]
    for seat_id in seat_ids:
        pairs.append(("seatIds", seat_id))
    if encrypted_seat_ids:
        pairs.append(("encryptedSeatIds", encrypted_seat_ids))
    if interlock_type_code:
        pairs.append(("interlockTypeCode", interlock_type_code))
    if interlock_tid:
        pairs.append(("interlockTid", interlock_tid))
    response = session.post(
        "https://tkglobal.melon.com/reservation/popup/stepTicket.htm?langCd=EN",
        data=encode_form_pairs(pairs),
        headers=headers,
        timeout=15,
    )
    return response


def refresh_tickettype_for_selected_seats(session, headers, base_form_body, seat_ids):
    pairs = parse_form_body(base_form_body)
    for seat_id in seat_ids:
        pairs.append(("seatId", seat_id))
    response = session.post(
        "https://tkglobal.melon.com/tktapi/glb/product/tickettype.json?v=1&callback=ticketTypeRefreshHandler",
        data=encode_form_pairs(pairs),
        headers=headers,
        timeout=15,
    )
    return extract_jsonp(response.text), response


def iter_ticket_type_rows(tickettype_data):
    seat_grade_list = tickettype_data.get("seatGradeList", []) if isinstance(tickettype_data, dict) else []
    for seat_grade in seat_grade_list:
        if not isinstance(seat_grade, dict):
            continue
        grade_no = str(seat_grade.get("seatGradeNo", "") or "")
        grade_name = str(
            seat_grade.get("seatGradeName")
            or seat_grade.get("seatGradeNm")
            or seat_grade.get("gradeName")
            or ""
        )
        prod_ticket_list = seat_grade.get("prodTicketTypeList", [])
        if isinstance(prod_ticket_list, list) and prod_ticket_list:
            for ticket in prod_ticket_list:
                if not isinstance(ticket, dict):
                    continue
                merged = dict(ticket)
                merged.setdefault("seatGradeNo", grade_no)
                merged.setdefault("seatGradeName", grade_name)
                merged.setdefault("basePrice", seat_grade.get("basePrice") or ticket.get("basePrice") or ticket.get("ticketTypePrice") or "")
                merged.setdefault("krPriceName", ticket.get("krPriceName") or ticket.get("priceName") or "")
                yield merged
        elif seat_grade.get("priceNo"):
            merged = dict(seat_grade)
            merged.setdefault("seatGradeNo", grade_no)
            merged.setdefault("seatGradeName", grade_name)
            merged.setdefault("krPriceName", seat_grade.get("krPriceName") or seat_grade.get("priceName") or "")
            yield merged

    prod_ticket_type_list = tickettype_data.get("prodTicketTypeList", []) if isinstance(tickettype_data, dict) else []
    for ticket in prod_ticket_type_list:
        if not isinstance(ticket, dict):
            continue
        yield dict(ticket)


def pick_selected_ticket(tickettype_data, seat_grade_no="", preferred_price_no=""):
    options = [ticket for ticket in iter_ticket_type_rows(tickettype_data) if ticket.get("priceNo")]
    if not options:
        return None

    def match(ticket, require_grade, require_price):
        grade_ok = str(ticket.get("seatGradeNo", "") or "") == str(seat_grade_no or "")
        price_ok = str(ticket.get("priceNo", "") or "") == str(preferred_price_no or "")
        if require_grade and not grade_ok:
            return False
        if require_price and not price_ok:
            return False
        return True

    for require_grade, require_price in (
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ):
        for ticket in options:
            if match(ticket, require_grade, require_price):
                return dict(ticket)
    return dict(options[0])


def build_selected_seatdata(tickettype_data, seat_id, seat_grade_no, clip_seat_id="0",
                            seat_name="", seat_grade_name=""):
    seat_list = tickettype_data.get("seatList", []) if isinstance(tickettype_data, dict) else []
    seatdata = []
    if isinstance(seat_list, list) and seat_list:
        for seat in seat_list:
            if not isinstance(seat, dict):
                continue
            seatdata.append({
                "sid": str(seat.get("seatId") or ""),
                "grade": str(seat.get("seatGradeNo") or seat_grade_no or ""),
                "title": str(seat.get("seatNo") or seat_name or seat_id),
                "csid": str(seat.get("clipSeatId") or "0"),
                "gn": str(seat.get("seatGradeName") or seat_grade_name or ""),
                "krTitle": str(seat.get("seatNo") or seat_name or seat_id),
            })
    if seatdata:
        return seatdata
    return [{
        "sid": str(seat_id),
        "grade": str(seat_grade_no or ""),
        "title": str(seat_name or seat_id),
        "csid": str(clip_seat_id or "0"),
        "gn": str(seat_grade_name or ""),
        "krTitle": str(seat_name or seat_id),
    }]


def pick_checkout_seat(refreshed_seatdata, preferred_grade_no="", fallback_seat_id="", fallback_clip_seat_id="0",
                       fallback_seat_name="", fallback_grade_name=""):
    for seat in refreshed_seatdata:
        if str(seat.get("sid") or "") == str(fallback_seat_id or ""):
            return {
                "sid": str(seat.get("sid") or fallback_seat_id),
                "grade": str(seat.get("grade") or preferred_grade_no or ""),
                "csid": str(seat.get("csid") or fallback_clip_seat_id or "0"),
                "title": str(seat.get("title") or fallback_seat_name or fallback_seat_id),
                "gn": str(seat.get("gn") or fallback_grade_name or ""),
                "krTitle": str(seat.get("krTitle") or seat.get("title") or fallback_seat_name or fallback_seat_id),
            }
    for seat in refreshed_seatdata:
        if str(seat.get("grade") or "") == str(preferred_grade_no or ""):
            return {
                "sid": str(seat.get("sid") or fallback_seat_id),
                "grade": str(seat.get("grade") or preferred_grade_no or ""),
                "csid": str(seat.get("csid") or fallback_clip_seat_id or "0"),
                "title": str(seat.get("title") or fallback_seat_name or fallback_seat_id),
                "gn": str(seat.get("gn") or fallback_grade_name or ""),
                "krTitle": str(seat.get("krTitle") or seat.get("title") or fallback_seat_name or fallback_seat_id),
            }
    if refreshed_seatdata:
        seat = refreshed_seatdata[0]
        return {
            "sid": str(seat.get("sid") or fallback_seat_id),
            "grade": str(seat.get("grade") or preferred_grade_no or ""),
            "csid": str(seat.get("csid") or fallback_clip_seat_id or "0"),
            "title": str(seat.get("title") or fallback_seat_name or fallback_seat_id),
            "gn": str(seat.get("gn") or fallback_grade_name or ""),
            "krTitle": str(seat.get("krTitle") or seat.get("title") or fallback_seat_name or fallback_seat_id),
        }
    return {
        "sid": str(fallback_seat_id),
        "grade": str(preferred_grade_no or ""),
        "csid": str(fallback_clip_seat_id or "0"),
        "title": str(fallback_seat_name or fallback_seat_id),
        "gn": str(fallback_grade_name or ""),
        "krTitle": str(fallback_seat_name or fallback_seat_id),
    }


def build_pricelimit_body(base_form_body, price_no, volume, chkcapt_raw):
    pairs = parse_form_body(base_form_body)
    pairs.append(("priceNo", price_no))
    pairs.append(("rsrvVolume", volume))
    pairs.append(("chkcapt", chkcapt_raw))
    return encode_form_pairs(pairs)


def load_step_delivery_page(session, headers, prod_id, schedule_no, first_seat_id):
    response = session.get(
        "https://tkglobal.melon.com/reservation/popup/stepDelvy.htm"
        f"?langCd=EN&prodId={prod_id}&scheduleNo={schedule_no}&firstSeatId={first_seat_id}",
        headers=headers,
        timeout=15,
    )
    return response


def choose_delivery_type_code(spot_recv_yn, global_mobile_recv_yn, global_delvy_yn):
    # Mirror stepDelvy.bindDelvyMethList() default checked radio.
    if str(global_delvy_yn or "N") == "Y":
        return "DV0006"
    if str(spot_recv_yn or "N") == "Y":
        return "DV0002"
    if str(global_mobile_recv_yn or "N") == "Y":
        return "DV0004"
    return "DV0002"


def calc_checkout_pay_amount(base_price, rsrv_fee, volume, delivery_type_code):
    delivery_cost = 0
    if str(delivery_type_code or "") == "DV0003":
        delivery_cost = 0
    return (int(base_price or 0) * int(volume or 0)) + (int(rsrv_fee or 0) * int(volume or 0)) + delivery_cost


def find_field(d, field_name, *sub_dicts):
    """在多个位置搜索字段值 (顶层 -> 各子字典)"""
    if not isinstance(d, dict):
        return ""
    val = d.get(field_name, "")
    if val:
        return str(val)
    for sub in sub_dicts:
        if isinstance(d.get(sub), dict):
            val = d[sub].get(field_name, "")
            if val:
                return str(val)
    return ""


def extract_price_no(d3):
    """
    从 tickettype 响应中提取 priceNo
    优先级: prodTicketTypeList > seatGradeList > 顶层字段
    """
    # 1) 优先从 prodTicketTypeList 提取 (指定席产品的 priceNo 在这里)
    ptt_list = d3.get("prodTicketTypeList", [])
    if isinstance(ptt_list, list):
        for ptt in ptt_list:
            pn = ptt.get("priceNo")
            if pn and str(pn) != "0":
                return str(pn)

    # 2) 从 seatGradeList 提取
    sgl = d3.get("seatGradeList", [])
    if isinstance(sgl, list):
        for sg in sgl:
            pn = sg.get("priceNo")
            if pn and str(pn) != "0":
                return str(pn)
            # 也可能在 seatGradeList 内嵌的 prodTicketTypeList
            inner_ptt = sg.get("prodTicketTypeList", [])
            if isinstance(inner_ptt, list):
                for iptt in inner_ptt:
                    pn = iptt.get("priceNo")
                    if pn and str(pn) != "0":
                        return str(pn)

    # 3) 顶层 priceNo
    pn = d3.get("priceNo")
    if pn and str(pn) != "0":
        return str(pn)

    return ""


def extract_pay_amt(d3):
    """从 tickettype 响应中提取价格"""
    # seatGradeList
    sgl = d3.get("seatGradeList", [])
    if isinstance(sgl, list):
        for sg in sgl:
            bp = sg.get("basePrice") or sg.get("price")
            if bp and str(bp) != "0":
                return str(bp)
    # prodTicketTypeList
    ptt_list = d3.get("prodTicketTypeList", [])
    if isinstance(ptt_list, list):
        for ptt in ptt_list:
            bp = ptt.get("basePrice") or ptt.get("price") or ptt.get("salePrice")
            if bp and str(bp) != "0":
                return str(bp)
    return ""


def interactive_select_seat(seat_list, preferred_section=""):
    """
    交互式选座: 打印可用区域，让用户手动输入选择
    返回 (seat_id, seat_grade_no, block_stats)
    """
    # 按 block 分组统计可用座位
    block_stats = defaultdict(lambda: {"total": 0, "available": 0, "seats": []})
    for seat in seat_list:
        sid = str(seat.get("seatId", ""))
        state = seat.get("seatStateCode", "")
        grade_no = seat.get("seatGradeNo", "")
        block_id = sid.split("_")[0] if "_" in sid else sid

        block_stats[block_id]["total"] += 1
        if state == "SA0001":  # 可用
            block_stats[block_id]["available"] += 1
            block_stats[block_id]["seats"].append(seat)
            if not block_stats[block_id].get("seatGradeNo"):
                block_stats[block_id]["seatGradeNo"] = str(grade_no)

    # 过滤出有可用座位的 block
    available_blocks = {k: v for k, v in block_stats.items() if v["available"] > 0}

    if not available_blocks:
        # 没有可用座位，返回第一个座位作为回退
        if seat_list:
            s = seat_list[0]
            return str(s.get("seatId", "")), str(s.get("seatGradeNo", "")), dict(block_stats)
        return "", "", {}

    sorted_blocks = sorted(available_blocks.items(), key=lambda x: x[1]["available"], reverse=True)
    
    print("\n  📍 =========== 有票区域列表 ===========")
    for i, (bid, info) in enumerate(sorted_blocks):
        print(f"     [{i+1}] Block {bid} (可用: {info['available']} / 总量: {info['total']})")
    print("  ========================================")
    
    choice = input("  ⌨️ 请输入你想抢的区域序号 (例如 1): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(sorted_blocks):
            selected_block = sorted_blocks[idx][0]
        else:
            print("  ⚠️ 输入范围无效，默认选择最高余票区域")
            selected_block = sorted_blocks[0][0]
    except ValueError:
        print("  ⚠️ 未输入有效数字，默认选择最高余票区域")
        selected_block = sorted_blocks[0][0]

    block_info = available_blocks[selected_block]
    chosen_seat = block_info["seats"][0]  # 选第一个可用座位
    print(f"  👉 已锁定区域: Block {selected_block}，分配到的真实精准座位号: {chosen_seat.get('seatId')}")

    return (str(chosen_seat.get("seatId", "")),
            str(chosen_seat.get("seatGradeNo", "")),
            dict(block_stats))


# ==========================================
# 主流程
# ==========================================
def main():
    ts = str(int(time.time() * 1000))
    referer_perf = f"https://tkglobal.melon.com/performance/index.htm?langCd=EN&prodId={PROD_ID}"
    referer_popup = "https://tkglobal.melon.com/reservation/popup/onestop.htm"

    print("=" * 60)
    print("🚀 Melon Ticket v8 - 自动适配 + 智能选座")
    print(f"📦 PROD_ID={PROD_ID}, SCHEDULE_NO={SCHEDULE_NO}, VOLUME={VOLUME}")
    if PREFERRED_SECTION:
        print(f"🎯 偏好区域: {PREFERRED_SECTION}")
    print("=" * 60)

    s = Session(impersonate=IMPERSONATE, proxies=PROXIES)
    for item in COOKIE.split('; '):
        kv = item.split('=', 1)
        if len(kv) == 2:
            s.cookies.set(kv[0], kv[1])

    h_get = {"Referer": referer_perf, "X-Requested-With": "XMLHttpRequest", "Accept": "*/*"}
    h_post = {**h_get, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
              "Origin": "https://tkglobal.melon.com"}

    # ================================================================
    # 步骤 A: 获取 memberKey
    # ================================================================
    print("\n📌 步骤A: POST getMemberKey.json")
    rA = s.post("https://tkglobal.melon.com/member/getMemberKey.json",
                data="", headers=h_post, timeout=10)
    dA = extract_jsonp(rA.text)
    if not dA or not dA.get("memberKey"):
        print(f"  ❌ 获取memberKey失败，请检查Cookie是否有效")
        print(f"  响应: {rA.text[:200]}")
        s.close()
        return
    member_key = str(dA["memberKey"])
    print(f"  ✅ memberKey={member_key}")

    # ================================================================
    # 步骤 B: 初始化购票弹窗会话
    # ================================================================
    print("\n📌 步骤B: POST onestop.htm (初始化购票弹窗会话)")
    onestop_data = (
        f"prodId={PROD_ID}"
        f"&prodTypeCode=PT0001"
        f"&scheduleNo={SCHEDULE_NO}"
        f"&pocCode={POC_CODE}"
        f"&perfTypeCode=GN0001"
        f"&sellTypeCode={SELL_TYPE_CODE}"
        f"&memberKey={member_key}"
        f"&langCd=EN"
    )
    rB = s.post("https://tkglobal.melon.com/reservation/popup/onestop.htm",
                data=onestop_data,
                headers={**h_post, "Referer": referer_perf}, timeout=10)
    with open("runtime_onestop.html", "w", encoding="utf-8") as f:
        f.write(rB.text)
    print(f"  status={rB.status_code}, body长度={len(rB.text)}")
    if rB.status_code == 200 and any(kw in rB.text.lower() for kw in ["onestop", "ticket", "seat"]):
        print(f"  ✅ 购票弹窗页面加载成功！")
    else:
        print(f"  ⚠️ 页面内容: {rB.text[:300]}")

    # 后续请求使用弹窗 Referer
    h_get2 = {"Referer": referer_popup, "X-Requested-With": "XMLHttpRequest", "Accept": "*/*"}
    h_post2 = {**h_get2, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
               "Origin": "https://tkglobal.melon.com"}

    # ================================================================
    # 步骤 1: prodKey
    # ================================================================
    print("\n📌 步骤1: GET prodKey.json")
    r1 = s.get(
        f"https://tkglobal.melon.com/tktapi/glb/product/prodKey.json"
        f"?callback=scheduleList8&prodId={PROD_ID}&scheduleNo={SCHEDULE_NO}&v=1&_={ts}",
        headers=h_get2, timeout=10)
    d1 = extract_jsonp(r1.text)
    traffic_ctrl = "N"
    if d1:
        traffic_ctrl = str(d1.get("trafficCtrlYn", "N"))
    print(f"  status={r1.status_code}, trafficCtrlYn={traffic_ctrl}")

    if traffic_ctrl.upper() == "Y":
        nfl_act_id = str(d1.get("nflActId", "")) if d1 else ""
        queue_key = ""
        print("\n📌 检测到 trafficCtrlYn=Y，开始处理 NetFunnel 排队...")

        if not nfl_act_id:
            print("  ⚠️ 未获取到 nflActId，跳过队列轮询并继续后续流程")
        else:
            while True:
                ts_queue = int(round(time.time() * 1000))
                if not queue_key:
                    queue_url = (
                        "https://zam.melon.com/ts.wseq?opcode=5101"
                        f"&nfid=0&prefix=NetFunnel.gRtype=5101;&ttl=2&sid=service_1&aid={nfl_act_id}"
                        f"&js=yes&user_data={member_key}&{ts_queue}"
                    )
                else:
                    queue_url = (
                        "https://zam.melon.com/ts.wseq?opcode=5002"
                        f"&key={queue_key}"
                        f"&nfid=0&prefix=NetFunnel.gRtype=5002;&ttl=2&sid=service_1&aid={nfl_act_id}"
                        f"&user_data={member_key}&js=yes&{ts_queue}"
                    )

                try:
                    queue_resp = s.get(queue_url, timeout=10)
                except Exception as e:
                    print(f"  ⚠️ 队列请求异常: {e}，1秒后重试")
                    time.sleep(1)
                    continue

                if queue_resp.status_code != 200:
                    print(f"  ⚠️ 队列请求状态异常: {queue_resp.status_code}，0.3秒后重试")
                    time.sleep(0.3)
                    continue

                queue_text = queue_resp.text
                wait_match = re.search(r"nwait=(\d+)", queue_text)
                key_match = re.search(r"key=([^&;]+)", queue_text)
                if key_match:
                    queue_key = key_match.group(1)

                if not wait_match:
                    print("  ⚠️ 未解析到 nwait，0.5秒后重试")
                    time.sleep(0.5)
                    continue

                wait_num = int(wait_match.group(1))
                if wait_num <= 0:
                    print("  ✅ 无需排队或排队结束，继续后续流程")
                    break

                print(f"  ⏳ 排队中，前方人数: {wait_num}")
                time.sleep(1)
    # ================================================================
    # 步骤 2: informProdSch → ⭐ 动态提取产品参数
    # ================================================================
    print("\n📌 步骤2: POST informProdSch.json ⭐ 动态提取产品参数")
    r2 = s.post(
        f"https://tkglobal.melon.com/tktapi/product/informProdSch.json?v=1",
        data=(f"prodId={PROD_ID}&pocCode={POC_CODE}&scheduleNo={SCHEDULE_NO}"
              f"&sellTypeCode={SELL_TYPE_CODE}&sellCondNo=&perfDate="),
        headers=h_post2, timeout=10)
    d2 = extract_jsonp(r2.text)
    if not d2 or d2.get("code") != "0000":
        print(f"  ❌ 获取产品信息失败")
        print(f"  响应: {json.dumps(d2, ensure_ascii=False)[:400] if d2 else r2.text[:300]}")
        s.close()
        return

    prod_inform = d2.get("prodInform", {})
    onestop_flplan_type_code = get_html_input_value(rB.text, "flplanTypeCode")
    onestop_seat_type_code = get_html_input_value(rB.text, "seatTypeCode")
    onestop_sell_cond_no = get_html_input_value(rB.text, "sellCondNo")
    onestop_netfunnel_key = get_html_input_value(rB.text, "netfunnel_key")

    perf_main_name = prod_inform.get("perfMainName", "")
    prod_type_code = find_field(d2, "prodTypeCode", "prodInform") or "PT0001"
    perf_type_code = find_field(d2, "perfTypeCode", "prodInform") or "GN0001"
    schedule_type_code = find_field(d2, "scheduleTypeCode", "prodInform") or "SG0001"
    flplan_type_code = find_field(d2, "flplanTypeCode", "prodInform") or onestop_flplan_type_code
    seat_type_code = find_field(d2, "seatTypeCode", "prodInform") or onestop_seat_type_code
    spot_recv_yn = find_field(d2, "spotRecvYn", "prodInform") or "N"
    global_mobile_recv_yn = find_field(d2, "globalMobileRecvYn", "prodInform") or "N"
    global_delvy_yn = find_field(d2, "globalDelvyYn", "prodInform") or "N"
    rsrv_fee = find_field(d2, "rsrvFee", "prodInform") or "0"
    sell_cond_no = onestop_sell_cond_no
    netfunnel_key = onestop_netfunnel_key

    perf_date = ""
    for key in ["perfStartDay", "perfDate", "perfDay"]:
        perf_date = find_field(d2, key, "prodInform")
        if perf_date:
            break

    is_designated = flplan_type_code == "DR0002"  # 指定席

    print(f"  ✅ 产品参数已自动提取:")
    print(f"     🎵 演出: {perf_main_name}")
    print(f"     📅 日期: {perf_date}")
    print(f"     🪑 座位类型: {'指定席' if is_designated else '自由席'} ({flplan_type_code})")
    print(f"     prodTypeCode:     {prod_type_code}")
    print(f"     perfTypeCode:     {perf_type_code}")
    print(f"     scheduleTypeCode: {schedule_type_code}")
    print(f"     seatTypeCode:     {seat_type_code}")
    print(f"     sellCondNo:       {sell_cond_no or '(empty)'}")
    print(f"     netfunnel_key:    {'present' if netfunnel_key else '(empty)'}")
    print(f"     delivery flags:   spotRecvYn={spot_recv_yn}, globalMobileRecvYn={global_mobile_recv_yn}, globalDelvyYn={global_delvy_yn}")
    print(f"     rsrvFee:          {rsrv_fee}")

    perf_main_name_enc = urllib.parse.quote(perf_main_name)

    # ================================================================
    # 步骤 3: tickettype → ⭐ 动态提取座位/价格/priceNo
    # ================================================================
    print("\n📌 步骤3: POST tickettype.json ⭐ 动态提取座位/价格")
    tt_body = (
        f"langCd=EN"
        f"&prodId={PROD_ID}"
        f"&pocCode={POC_CODE}"
        f"&perfTypeCode={perf_type_code}"
        f"&perfDate={perf_date}"
        f"&scheduleNo={SCHEDULE_NO}"
        f"&sellTypeCode={SELL_TYPE_CODE}"
        f"&sellCondNo={sell_cond_no}"
        f"&perfMainName={perf_main_name_enc}"
        f"&seatGradeNo="
        f"&seatGradeName="
        f"&blockId="
        f"&sntv="
        f"&blockTypeCode="
        f"&floorNo="
        f"&floorName="
        f"&areaNo="
        f"&areaName="
        f"&prodTypeCode={prod_type_code}"
        f"&flplanTypeCode={flplan_type_code}"
        f"&scheduleTypeCode={schedule_type_code}"
        f"&seatTypeCode={seat_type_code}"
        f"&jType=I"
        f"&cardGroupId="
        f"&cardBpId="
        f"&cardMid="
        f"&rsrvStep=SAT"
        f"&zamEnabled=0"
        f"&zamKey="
        f"&trafficCtrlYn={traffic_ctrl}"
        f"&netfunnel_key={urllib.parse.quote(netfunnel_key)}"
        f"&stvn_view_list="
        f"&mapClickYn=N"
    )
    tt_body_probe = tt_body
    if flplan_type_code == "DR0002" and not seat_type_code:
        probe_pairs = upsert_form_field(parse_form_body(tt_body), "seatTypeCode", "SE0003")
        tt_body_probe = encode_form_pairs(probe_pairs)
        print("  probe tickettype uses seatTypeCode=SE0003 to enumerate seats before prodlimit")
    r3 = s.post(
        f"https://tkglobal.melon.com/tktapi/glb/product/tickettype.json?v=1&callback=jQuery36003{ts}",
        data=tt_body_probe, headers=h_post2, timeout=10)
    d3 = extract_jsonp(r3.text)
    if not d3 or d3.get("code") != "0000":
        print(f"  ❌ tickettype 失败")
        print(f"  响应: {json.dumps(d3, ensure_ascii=False)[:500] if d3 else r3.text[:300]}")
        s.close()
        return

    seat_list = d3.get("seatList", [])
    seat_grade_list = d3.get("seatGradeList", [])
    limit_volume = d3.get("limitVolume", {})

    # ⭐ 提取 priceNo: 优先从 prodTicketTypeList
    price_no = extract_price_no(d3)
    pay_amt = extract_pay_amt(d3)

    # ⭐ 交互式选座: 用户看列表后手动输入选择
    seat_id, seat_grade_no, block_stats = interactive_select_seat(seat_list, PREFERRED_SECTION)

    if not seat_id:
        print(f"  ❌ 没有找到任何座位数据")
        s.close()
        return

    # 统计可用区域
    avail_blocks = {k: v for k, v in block_stats.items() if v["available"] > 0}
    total_avail = sum(v["available"] for v in avail_blocks.values())

    print(f"  ✅ 座位/价格信息已自动提取:")
    print(f"     🪑 选中seatId:    {seat_id}")
    print(f"     🎫 seatGradeNo:   {seat_grade_no}")
    print(f"     💰 priceNo:       {price_no}")
    print(f"     💵 payAmt:        {pay_amt}")
    print(f"     📊 总座位数:      {len(seat_list)}")
    print(f"     📊 可用座位总数:  {total_avail}")
    print(f"     📊 有票区域数:    {len(avail_blocks)}")
    print(f"     📊 限购:          {limit_volume.get('LIMITVOLUME', '?')} 张")

    if avail_blocks:
        print(f"     📍 有票区域 (blockId: 可用/总数):")
        for bid in sorted(avail_blocks, key=lambda b: avail_blocks[b]["available"], reverse=True)[:10]:
            info = avail_blocks[bid]
            marker = " ← 已选" if bid == seat_id.split("_")[0] else ""
            print(f"        block {bid}: {info['available']}/{info['total']}{marker}")

    real_seat = {}
    selected_context_fields = {}
    if is_designated:
        block_id = seat_id.split("_")[0] if "_" in seat_id else seat_id
        print(f"\n  🔄 指定席需要二次进入 stepBlock，获取 block {block_id} 的实时真座位...")
        real_seat, seat_map_result, seat_map_debug, selected_block_context = fetch_designated_seat(
            s,
            h_get2,
            h_post2,
            PROD_ID,
            SCHEDULE_NO,
            POC_CODE,
            block_id,
            seat_grade_no,
        )
        if not real_seat:
            print("  ❌ stepBlock 实时座位获取失败，当前 block 没拿到可下单 seatId。")
            print(f"  调试信息: {seat_map_debug}")
            if seat_map_result:
                print(f"  seatMap code: {seat_map_result.get('code', 'unknown')}")
            s.close()
            return

        seat_id = real_seat["seatId"]
        seat_grade_no = real_seat["seatGradeNo"] or seat_grade_no
        clip_seat_id = real_seat["clipSeatId"]
        mapped_seat_type_code = str(real_seat.get("seatTypeCode") or "")
        if mapped_seat_type_code and mapped_seat_type_code != seat_type_code:
            print(f"  updated seatTypeCode from live seat map: {seat_type_code or '(empty)'} -> {mapped_seat_type_code}")
            seat_type_code = mapped_seat_type_code
        if not seat_type_code:
            seat_type_code = "SE0001"
            print("  fallback designated seatTypeCode -> SE0001")
        if selected_block_context.get("sntv"):
            sntv_parts = str(selected_block_context["sntv"]).split(",", 1)
            if not selected_block_context.get("floorNo") and len(sntv_parts) >= 1:
                selected_block_context["floorNo"] = sntv_parts[0]
            if not selected_block_context.get("areaNo") and len(sntv_parts) == 2:
                selected_block_context["areaNo"] = sntv_parts[1]
        if selected_block_context.get("floorNo") and not selected_block_context.get("floorName"):
            selected_block_context["floorName"] = "층"
        if selected_block_context.get("areaNo") and not selected_block_context.get("areaName"):
            selected_block_context["areaName"] = "구역"
        if selected_block_context.get("sntv") and not selected_block_context.get("blockTypeCode"):
            selected_block_context["blockTypeCode"] = "undefined"
        selected_context_fields = {
            "seatGradeNo": seat_grade_no,
            "blockId": block_id,
            "sntv": selected_block_context.get("sntv", ""),
            "blockTypeCode": selected_block_context.get("blockTypeCode", ""),
            "floorNo": selected_block_context.get("floorNo", ""),
            "floorName": selected_block_context.get("floorName", ""),
            "areaNo": selected_block_context.get("areaNo", ""),
            "areaName": selected_block_context.get("areaName", ""),
        }
        tt_body = build_post_lock_form_body(
            tt_body,
            seat_type_code=seat_type_code,
            extra_fields=selected_context_fields,
        )
        print(
            "  synced designated context into sForm body: "
            f"seatGradeNo={selected_context_fields.get('seatGradeNo')}, "
            f"blockId={selected_context_fields.get('blockId')}, "
            f"sntv={selected_context_fields.get('sntv') or '(empty)'}, "
            f"floorNo={selected_context_fields.get('floorNo') or '(empty)'}, "
            f"areaNo={selected_context_fields.get('areaNo') or '(empty)'}, "
            f"seatTypeCode={seat_type_code or '(empty)'}"
        )
        print(
            "  ✅ 已切换到实时座位: "
            f"seatId={seat_id}, seatGradeNo={seat_grade_no}, seatName={real_seat['seatName']}"
        )
    else:
        clip_seat_id = "0"

    tt_body_after_lock = tt_body

    # 如果 priceNo 还是空，尝试 summary.json 补充
    if not price_no:
        print(f"\n  ⚠️ priceNo 未从 tickettype 获取到，尝试 summary.json...")
        r_sum = s.post(
            f"https://tkglobal.melon.com/tktapi/glb/product/summary.json?v=1",
            data=f"prodId={PROD_ID}&scheduleNo={SCHEDULE_NO}&seatGradeNo={seat_grade_no}",
            headers=h_post2, timeout=10)
        d_sum = extract_jsonp(r_sum.text)
        if d_sum:
            print(f"  summary响应: {json.dumps(d_sum, ensure_ascii=False, indent=2)[:500]}")
            for key in ["priceList", "priceTypeList", "priceInfo", "prodTicketTypeList"]:
                pl = d_sum.get(key, [])
                if isinstance(pl, list) and pl:
                    for item in pl:
                        pn = item.get("priceNo")
                        if pn and str(pn) != "0":
                            price_no = str(pn)
                            break
                if price_no:
                    break
            if not price_no:
                price_no = str(d_sum.get("priceNo", ""))
            if not pay_amt:
                pay_amt = str(d_sum.get("basePrice", d_sum.get("price", "")))

    if not price_no or price_no == "0":
        print(f"  ❌ 无法获取有效的 priceNo！")
        print(f"  提示: 完整tickettype响应键: {list(d3.keys())}")
        print(f"  prodTicketTypeList: {json.dumps(d3.get('prodTicketTypeList', []), ensure_ascii=False)[:500]}")
        s.close()
        return

    print(f"\n  📋 最终参数确认: seatId={seat_id}, priceNo={price_no}, payAmt={pay_amt}")

    # ================================================================
    # 步骤 4: seatStateInfo (仅自由席使用)
    # ================================================================
    if is_designated:
        print("\n📌 步骤4: 跳过 seatStateInfo.json")
        print(f"  ℹ️ 当前为指定席流程，seatTypeCode={seat_type_code}。前端实际先走 prodlimit.json 锁座，不在这里拦截。")
    else:
        print("\n📌 步骤4: POST seatStateInfo.json (内部检查)")
        r4 = s.post(
            f"https://tkglobal.melon.com/tktapi/product/seatStateInfo.json?v=1&callback=jQuery36004{ts}",
            data=f"prodId={PROD_ID}&scheduleNo={SCHEDULE_NO}&seatId={seat_id}&volume={VOLUME}&selectedGradeVolume={VOLUME}",
            headers=h_post2, timeout=10)
        d4 = extract_jsonp(r4.text)
        print(f"  status={r4.status_code}")
        if d4:
            rmd = d4.get("rmdSeatCnt", "?")
            chk = d4.get("chkResult", "?")
            print(f"  rmdSeatCnt={rmd}, chkResult={chk}")
            if str(rmd) == "0" or str(chk) == "0":
                print("  ❌ (步骤4) seatStateInfo 返回不可用，当前 seatId 不能继续下单。")
                s.close()
                return
        else:
            print(f"  ⚠️ 非JSON响应: {r4.text[:200]}")

    # ================================================================
    # 步骤 4.5: 验证码处理 (Secure Booking Service) - 全自动循环破解
    # ================================================================
    print("\n📌 步骤4.5: GET captChaImage.json ⭐ 全自动识别验证码")
    
    chkcapt_val = ""
    chkcapt_raw = ""
    req_captcha = False
    
    try:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
    except Exception as e:
        print(f"  ❌ 无法加载 ddddocr，无法自动过验证码！报错: {e}")
        ocr = None

    max_auto_attempts = 3
    for attempt in range(max_auto_attempts + 1):
        is_manual = attempt == max_auto_attempts
        t_msec = str(int(time.time() * 1000))
        r_cap_img = s.get(
            f"https://tkglobal.melon.com/reservation/ajax/captChaImage.json?prodId={PROD_ID}&scheduleNo={SCHEDULE_NO}&t={t_msec}",
            headers=h_get2, timeout=10)
        d_cap_img = extract_jsonp(r_cap_img.text)
        
        if d_cap_img and "CAPTDATA" in d_cap_img:
            req_captcha = True
            capt_data = d_cap_img["CAPTDATA"]
            capt_img_b64 = d_cap_img.get("CAPTIMAGE", "")
            if capt_img_b64:
                import base64
                with open("captcha.png", "wb") as f:
                    captcha_bytes = base64.b64decode(capt_img_b64)
                    f.write(captcha_bytes)

                user_capt = ""
                if not is_manual and ocr:
                    print(f"  ⚠️ [第 {attempt+1} 次尝试] 获取验证码成功，开始提取 alpha 通道并批量识别...")
                    guesses = build_captcha_ocr_candidates(captcha_bytes, ocr)[:3]
                    if guesses:
                        print(f"  🤖 OCR 候选: {[guess for _, guess in guesses]}")
                    else:
                        print("  ⚠️ OCR 没有产出有效候选，自动换一张...")
                        time.sleep(1)
                        continue

                    for variant_name, guess in guesses:
                        print(f"  🔍 尝试候选 [{variant_name}] -> {guess}")
                        d_cap_chk = verify_captcha_guess(
                            s,
                            h_post2,
                            PROD_ID,
                            SCHEDULE_NO,
                            POC_CODE,
                            SELL_TYPE_CODE,
                            guess,
                            urllib.parse.quote(capt_data),
                        )
                        if d_cap_chk and d_cap_chk.get("CODE") == "0000":
                            user_capt = guess
                            chkcapt_source = d_cap_chk.get("DATA") or capt_data
                            chkcapt_raw = chkcapt_source
                            chkcapt_val = urllib.parse.quote(chkcapt_source)
                            print(f"  ✅ 验证码 [{user_capt}] 校验通过！突破封锁！")
                            print(f"  🔐 已升级 captcha token，长度={len(chkcapt_source)}")
                            break
                    if user_capt:
                        break

                    print("  ❌ 当前验证码的 OCR 候选全部被服务端拒绝，自动换一张...")
                    chkcapt_val = ""
                    chkcapt_raw = ""
                    time.sleep(1)
                    continue
                else:
                    print(f"\n  🚨 ddddocr 已经被 Melon 的新型干扰线彻底击溃 (3次全部识别为空)！")
                    print("  🚨 为了保住刚才抢到的真实座位，不得不切入紧急手动模式！")
                    try:
                        os.startfile("captcha.png")  # Windows 自动弹出图片
                    except:
                        pass
                    user_capt = input("  ⌨️ 验证码已弹窗，请火速手动打字输入 (注意大写): ").strip()
                    if not user_capt:
                        print("  ❌ 放弃抢票。")
                        s.close()
                        return

                user_capt = normalize_captcha_text(user_capt)
                d_cap_chk = verify_captcha_guess(
                    s, h_post2, PROD_ID, SCHEDULE_NO, POC_CODE, SELL_TYPE_CODE, user_capt, urllib.parse.quote(capt_data)
                )
                if d_cap_chk and d_cap_chk.get("CODE") == "0000":
                    chkcapt_source = d_cap_chk.get("DATA") or capt_data
                    chkcapt_raw = chkcapt_source
                    chkcapt_val = urllib.parse.quote(chkcapt_source)
                    print(f"  ✅ 验证码 [{user_capt}] 校验通过！突破封锁！")
                    print(f"  🔐 已升级 captcha token，长度={len(chkcapt_source)}")
                    break
                else:
                    print(f"  ❌ 验证码 [{user_capt}] 服务端返回错误...")
                    chkcapt_val = ""
                    chkcapt_raw = ""
                    time.sleep(1)
        else:
            print("  ✅ 未要求验证码")
            break

    if req_captcha and not chkcapt_raw:
        print("  ❌ 验证码流程彻底失败，直接中止。")
        s.close()
        return

    # ================================================================
    # 步骤 4.6: prodlimit (指定席真实锁座)
    # ================================================================
    interlock_type_code = ""
    interlock_tid = ""
    encrypted_seat_ids = ""
    if is_designated:
        print("\n📌 步骤4.6: POST prodlimit.json ⭐ 指定席锁座")
        d_prodlimit, r_prodlimit = submit_designated_prodlimit(
            s,
            h_post2,
            tt_body,
            seat_id,
            clip_seat_id,
            chkcapt_val,
        )
        print(f"  status={r_prodlimit.status_code}")
        if d_prodlimit:
            result_code = d_prodlimit.get("result") or d_prodlimit.get("code", "?")
            print(f"  code={result_code}")
            if str(result_code) == "0000":
                encrypted_seat_ids = str(d_prodlimit.get("encryptedSeatIds", "") or "")
                interlock_type_code = str(d_prodlimit.get("interlockTypeCode", "") or "")
                interlock_tid = str(d_prodlimit.get("interlockTid", "") or "")
                tt_body_after_lock = build_post_lock_form_body(
                    tt_body,
                    encrypted_seat_ids=encrypted_seat_ids,
                    interlock_type_code=interlock_type_code,
                    interlock_tid=interlock_tid,
                    seat_type_code=seat_type_code,
                    extra_fields=selected_context_fields,
                )
                print(
                    "  ✅ prodlimit 锁座成功: "
                    f"encryptedSeatIds={'yes' if encrypted_seat_ids else 'no'}, "
                    f"interlockTypeCode={interlock_type_code or '(empty)'}"
                )
            else:
                print(f"  ❌ prodlimit 失败: {json.dumps(d_prodlimit, ensure_ascii=False)[:500]}")
                s.close()
                return
        else:
            print(f"  ❌ prodlimit 非JSON响应: {r_prodlimit.text[:300]}")
            s.close()
            return

    # ================================================================
    # 步骤 5: delivery (配送方式)
    # ================================================================
    # Step 5: rebuild stepTicket state after prodlimit
    # ================================================================
    print("\n[Step 5] POST tickettype.json (refresh after prodlimit)")
    r_step_ticket = post_step_ticket_page(
        s,
        h_post2,
        PROD_ID,
        SCHEDULE_NO,
        flplan_type_code,
        seat_type_code,
        [seat_id],
        encrypted_seat_ids,
        interlock_type_code,
        interlock_tid,
    )
    print(
        "  stepTicket post context: "
        f"prodId={PROD_ID}, scheduleNo={SCHEDULE_NO}, "
        f"seatTypeCode={seat_type_code or '(empty)'}, "
        f"encryptedSeatIds={'yes' if encrypted_seat_ids else 'no'}"
    )
    print(f"  stepTicket status={r_step_ticket.status_code}")
    with open("runtime_stepTicket.html", "w", encoding="utf-8") as f:
        f.write(r_step_ticket.text)

    selected_ticket = {
        "priceNo": str(price_no),
        "seatGradeNo": str(seat_grade_no),
        "seatGradeName": str(real_seat.get("seatGradeName") or ""),
        "basePrice": str(pay_amt),
        "ticketTypePrice": str(pay_amt),
        "krPriceName": "",
        "priceName": "",
        "sejongPriceCode": "",
        "selectedVolume": str(VOLUME),
    }
    refreshed_seatdata = build_selected_seatdata(
        {},
        seat_id,
        seat_grade_no,
        clip_seat_id,
        real_seat.get("seatName", ""),
        real_seat.get("seatGradeName", ""),
    )

    d3_refresh, r3_refresh = refresh_tickettype_for_selected_seats(
        s,
        h_post2,
        tt_body_after_lock,
        [seat_id],
    )
    print(f"  tickettype status={r3_refresh.status_code}")
    if d3_refresh and d3_refresh.get("code") == "0000":
        picked_ticket = pick_selected_ticket(d3_refresh, seat_grade_no, price_no)
        if picked_ticket:
            picked_ticket["selectedVolume"] = str(VOLUME)
            selected_ticket = picked_ticket
            price_no = str(picked_ticket.get("priceNo") or price_no)
            pay_amt = str(
                picked_ticket.get("ticketTypePrice")
                or picked_ticket.get("basePrice")
                or pay_amt
            )
        refreshed_seatdata = build_selected_seatdata(
            d3_refresh,
            seat_id,
            seat_grade_no,
            clip_seat_id,
            real_seat.get("seatName", ""),
            real_seat.get("seatGradeName", ""),
        )
        print(
            "  OK refreshed tickettype: "
            f"priceNo={price_no}, payAmt={pay_amt}, seatdata={len(refreshed_seatdata)}"
        )
        seat_list_refresh = d3_refresh.get("seatList", []) if isinstance(d3_refresh, dict) else []
        if isinstance(seat_list_refresh, list) and seat_list_refresh:
            refreshed_seat_type_code = extract_seat_type_code(d3_refresh, seat_id)
            if refreshed_seat_type_code and refreshed_seat_type_code != seat_type_code:
                print(f"  updated seatTypeCode from refreshed tickettype: {seat_type_code or '(empty)'} -> {refreshed_seat_type_code}")
                seat_type_code = refreshed_seat_type_code
                tt_body_after_lock = build_post_lock_form_body(
                    tt_body,
                    encrypted_seat_ids=encrypted_seat_ids,
                    interlock_type_code=interlock_type_code,
                    interlock_tid=interlock_tid,
                    seat_type_code=seat_type_code,
                    extra_fields=selected_context_fields,
                )
            first_ids = [str(item.get("seatId") or "") for item in seat_list_refresh[:8] if isinstance(item, dict)]
            locked_match_indexes = [
                idx for idx, item in enumerate(seat_list_refresh)
                if isinstance(item, dict) and str(item.get("seatId") or "") == str(seat_id)
            ][:5]
            print(f"  debug refreshed seatList first ids: {first_ids}")
            print(f"  debug locked seat index in refreshed seatList: {locked_match_indexes if locked_match_indexes else 'not_found'}")
    else:
        print("  WARN refreshed tickettype did not return clean JSON; continue with fallback ticket data")
        print(f"  response: {json.dumps(d3_refresh, ensure_ascii=False)[:300] if d3_refresh else r3_refresh.text[:200]}")

    if is_designated:
        checkout_seat = {
            "sid": str(seat_id),
            "grade": str(selected_ticket.get("seatGradeNo") or seat_grade_no or ""),
            "csid": str(clip_seat_id or "0"),
            "title": str(real_seat.get("seatName") or seat_id),
            "gn": str(selected_ticket.get("seatGradeName") or real_seat.get("seatGradeName") or ""),
            "krTitle": str(real_seat.get("seatName") or seat_id),
        }
    else:
        checkout_seat = pick_checkout_seat(
            refreshed_seatdata,
            selected_ticket.get("seatGradeNo") or seat_grade_no,
            seat_id,
            clip_seat_id,
            real_seat.get("seatName", ""),
            real_seat.get("seatGradeName", ""),
        )
    checkout_seat_id = checkout_seat["sid"] or seat_id
    checkout_clip_seat_id = checkout_seat["csid"] or clip_seat_id or "0"
    print(
        "  checkout seat resolved: "
        f"lockSeatId={seat_id}, paySeatId={checkout_seat_id}, "
        f"lockClipSeatId={clip_seat_id or '0'}, payClipSeatId={checkout_clip_seat_id}, "
        f"grade={checkout_seat.get('grade') or seat_grade_no}"
    )

    # ================================================================
    # Step 5.5: pricelimit using stepTicket.chkPriceLimit semantics
    # ================================================================
    print("\n[Step 5.5] POST pricelimit.json")
    pl_body = build_pricelimit_body(tt_body_after_lock, price_no, VOLUME, chkcapt_raw)
    r55 = s.post(
        "https://tkglobal.melon.com/tktapi/glb/reservation/pricelimit.json?v=1&callback=priceLimitHandler",
        data=pl_body,
        headers=h_post2,
        timeout=10,
    )
    d55 = extract_jsonp(r55.text)
    print(f"  status={r55.status_code}")
    if d55:
        price_limit_code = str(d55.get("result") or d55.get("code") or "?")
        print(f"  code={price_limit_code}, limitVolume={d55.get('limitVolume', '?')}")
        if price_limit_code != "0000":
            print(f"  FAIL pricelimit blocked: {json.dumps(d55, ensure_ascii=False)[:500]}")
            s.close()
            return
    else:
        print(f"  FAIL non-JSON response (status={r55.status_code}): {r55.text[:300]}")
        s.close()
        return

    # ================================================================
    # Step 6: load stepDelvy page and initialize delivery state
    # ================================================================
    print("\n[Step 6] GET stepDelvy.htm")
    r_delvy_page = load_step_delivery_page(s, h_get2, PROD_ID, SCHEDULE_NO, checkout_seat_id)
    print(f"  status={r_delvy_page.status_code}, body_length={len(r_delvy_page.text)}")
    with open("runtime_stepDelvy.html", "w", encoding="utf-8") as f:
        f.write(r_delvy_page.text)
    sell_cond_no = sell_cond_no or get_html_input_value(r_delvy_page.text, "sellCondNo")
    netfunnel_key = netfunnel_key or get_html_input_value(r_delvy_page.text, "netfunnel_key")

    print("\n[Step 6.5] POST delivery.json")
    tt_body_with_seat = tt_body_after_lock + f"&seatId={checkout_seat_id}"
    tt_body_delvy = tt_body_with_seat
    delivery_pairs = parse_form_body(tt_body_delvy)
    delivery_debug = {k: v for k, v in delivery_pairs if k in {"seatGradeNo", "blockId", "sntv", "seatTypeCode", "encryptedSeatIds", "interlockTypeCode", "seatId", "rsrvStep"}}
    print(f"  delivery sForm context: {delivery_debug}")
    r5 = s.post(
        f"https://tkglobal.melon.com/tktapi/glb/product/delivery.json?v=1&callback=jQuery36005{ts}",
        data=tt_body_delvy,
        headers=h_post2,
        timeout=10,
    )
    d5 = extract_jsonp(r5.text)
    print(f"  status={r5.status_code}")
    if d5:
        code5 = str(d5.get("code") or d5.get("result") or "?")
        print(f"  code={code5}")
        card_list = d5.get("cardBpList", [])
        if card_list:
            print(f"  payment options: {[c.get('cardBpId') for c in card_list[:3]]}")
        selected_card_meta = get_selected_card_meta(d5)
        print(
            "  selected card: "
            f"cardCode={selected_card_meta['card_code']}, "
            f"cardCodeName={selected_card_meta['card_name']}, "
            f"autheTypeCode={selected_card_meta['authe_type_code'] or '(empty)'}, "
            f"quota={selected_card_meta['quota']}"
        )
    else:
        print(f"  WARN non-JSON response: {r5.text[:200]}")
        selected_card_meta = {
            "card_code": "FOREIGN_CHINABANK",
            "card_name": "UnionPay",
            "authe_type_code": "",
            "card_quota": "12",
            "quota": "00",
            "card_bp_id": "FOREIGN_CHINABANK",
            "card_mid": "",
        }

    # ================================================================
    # Step 7: build stepDelvy-style payParams
    # ================================================================
    seat_grade_name = str(
        selected_ticket.get("seatGradeName")
        or real_seat.get("seatGradeName")
        or checkout_seat.get("gn")
        or ""
    )
    seat_name_for_save = "\ube44\uc9c0\uc815" if seat_type_code == "SE0003" else str(
        checkout_seat.get("krTitle")
        or real_seat.get("seatName")
        or seat_id
    )
    seat_info_price_no = int(price_no) if str(price_no).isdigit() else str(price_no)
    seat_info_base_price = selected_ticket.get("basePrice") or selected_ticket.get("ticketTypePrice") or pay_amt
    seat_info_base_price = int(seat_info_base_price) if str(seat_info_base_price).isdigit() else seat_info_base_price
    seat_info_sejong_price_code = selected_ticket.get("sejongPriceCode")
    if seat_info_sejong_price_code in ("", None):
        seat_info_sejong_price_code = None
    seat_info_list = [{
        "priceNo": seat_info_price_no,
        "seatId": str(checkout_seat_id),
        "clipSeatId": "0" if seat_type_code == "SE0003" else str(checkout_clip_seat_id or "0"),
        "gradeNm": seat_grade_name,
        "seatNm": seat_name_for_save,
        "basePrice": seat_info_base_price,
        "priceName": str(selected_ticket.get("krPriceName") or selected_ticket.get("priceName") or ""),
        "sejongPriceCode": seat_info_sejong_price_code,
    }]

    delivery_type_code = choose_delivery_type_code(
        spot_recv_yn,
        global_mobile_recv_yn,
        global_delvy_yn,
    )
    pay_amt = str(calc_checkout_pay_amount(
        selected_ticket.get("basePrice") or selected_ticket.get("ticketTypePrice") or pay_amt,
        rsrv_fee,
        VOLUME,
        delivery_type_code,
    ))
    print(f"  selected delivery type: {delivery_type_code}")
    print(f"  recalculated pay amount: {pay_amt}")

    seat_info_json = json.dumps(
        seat_info_list,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    # stepDelvy builds payParams in two stages:
    # 1) $("#dForm").serializeArray() for visible/checked form controls
    # 2) append reservation-specific fields (prodId/priceNo/seatInfoList/etc.)
    base_save_pairs = [
        ("jType", "I"),
        ("delvyTypeCode", delivery_type_code),
        ("tel", USER_PHONE),
        ("email", USER_EMAIL),
        ("recv_country", ""),
        ("recv_name", ""),
        ("recv_address", ""),
        ("recv_city", ""),
        ("recv_state", ""),
        ("recv_zipno", ""),
        ("recv_tel1", ""),
        ("recv_tel2", ""),
        ("recv_country_code", ""),
        ("recv_delvy_price", "0"),
        ("addAddress", ""),
        ("payMethodCode", "AP0012"),
        ("cardCode", selected_card_meta["card_code"]),
        ("cardCodeName", selected_card_meta["card_name"]),
        ("autheTypeCode", selected_card_meta["authe_type_code"]),
        ("cardQuota", selected_card_meta["card_quota"]),
        ("quota", selected_card_meta["quota"]),
        ("chkAgree", "on"),
        ("chkAgree", "on"),
        ("chkAgree", "on"),
        ("chkAgree", "on"),
        ("chkAgree", "on"),
        ("chkAgree", "on"),
        ("prodId", PROD_ID),
        ("pocCode", POC_CODE),
        ("scheduleNo", SCHEDULE_NO),
        ("rsrvVolume", VOLUME),
        ("payAmt", pay_amt),
        ("cardBpId", selected_card_meta["card_bp_id"]),
        ("cardMid", selected_card_meta["card_mid"]),
    ]
    if seat_type_code == "SE0003" and sell_cond_no:
        base_save_pairs.append(("drawOrderNo", sell_cond_no))
    for _ in range(int(VOLUME)):
        base_save_pairs.append(("priceNo", price_no))
        base_save_pairs.append(("seatId", checkout_seat_id))
        base_save_pairs.append(("advtkNo", ""))
    base_save_pairs.append(("seatInfoListWithPriceType", seat_info_json))
    if netfunnel_key:
        base_save_pairs.append(("netfunnel_key", netfunnel_key))

    # ================================================================
    # Step 8: getNoRsrvSeq / save
    # ================================================================
    requires_no_rsrv_seq = flplan_type_code == "DR0003" or seat_type_code == "SE0003"
    save_pairs = list(base_save_pairs)
    if requires_no_rsrv_seq:
        print("\n[Step 8] POST getNoRsrvSeq.json")
        with open("debug_getNoRsrvSeq_body.txt", "w", encoding="utf-8") as f:
            f.write(encode_form_pairs(base_save_pairs))
        r6 = s.post(
            "https://tkglobal.melon.com/tktapi/glb/reservation/getNoRsrvSeq.json?v=1&callback=getNoRsrvSeqHandler",
            data=encode_form_pairs(base_save_pairs),
            headers=h_post2,
            timeout=10,
        )
        d6 = extract_jsonp(r6.text)
        code6 = str(d6.get('code', '?')) if d6 else '?'
        msg6 = d6.get('message', '') if d6 else ''
        print(f"  status={r6.status_code}, code={code6}")
        if msg6:
            print(f"  message: {msg6}")
        if not d6 or code6 != "0000" or not d6.get("noRsrvSeatSeqs"):
            print(f"  FAIL getNoRsrvSeq: {json.dumps(d6, ensure_ascii=False)[:500] if d6 else r6.text[:300]}")
            print("  debug: trying direct save without noRsrvSeatSeq for comparison...")
            r7_probe = s.post(
                "https://tkglobal.melon.com/tktapi/glb/reservation/save.json?v=1&callback=saveHandler",
                data=encode_form_pairs(save_pairs),
                headers=h_post2,
                timeout=15,
            )
            d7_probe = extract_jsonp(r7_probe.text)
            print(f"  direct save status={r7_probe.status_code}")
            print(f"  direct save response: {json.dumps(d7_probe, ensure_ascii=False)[:500] if d7_probe else r7_probe.text[:300]}")
            s.close()
            return
        for seq in d6.get("noRsrvSeatSeqs", []):
            save_pairs.append(("noRsrvSeatSeq", seq))
        save_pairs.append(("firstSeatId", checkout_seat_id))
        save_pairs.append(("sellTypeCode", SELL_TYPE_CODE))
        save_pairs.append(("chkcapt", chkcapt_raw))
        if interlock_type_code == "IL0003":
            save_pairs.append(("interlockTid", d6.get("interlockTid") or interlock_tid))
    else:
        save_pairs.append(("firstSeatId", checkout_seat_id))
        save_pairs.append(("sellTypeCode", SELL_TYPE_CODE))
        save_pairs.append(("chkcapt", chkcapt_raw))
        if interlock_type_code == "IL0003" and interlock_tid:
            save_pairs.append(("interlockTid", interlock_tid))

    print("\n[Step 9] POST save.json")
    with open("debug_save_body.txt", "w", encoding="utf-8") as f:
        f.write(encode_form_pairs(save_pairs))
    r7 = s.post(
        "https://tkglobal.melon.com/tktapi/glb/reservation/save.json?v=1&callback=saveHandler",
        data=encode_form_pairs(save_pairs),
        headers=h_post2,
        timeout=15,
    )
    d7 = extract_jsonp(r7.text)
    print(f"  status={r7.status_code}")
    print(f"  response: {json.dumps(d7, ensure_ascii=False, indent=2)[:600] if d7 else r7.text[:400]}")

    if d7 and (str(d7.get('result', '')).lower() == 'true' or d7.get('code') == '0000'):
        print("\n  SUCCESS order submitted")
        print("  LINK https://tkglobal.melon.com/myticket/rsrvList.htm?langCd=EN")

        pay_method_code = str(d7.get("payMethodCode") or "AP0012")
        if pay_method_code in {"AP0001", "AP0012", "AP0010", "AP0011"}:
            print("\n[Step 10] POST payInitForm.htm")
            pay_init_payload = dict(d7)
            pay_init_payload["card_pay_method"] = "GLB"
            r_pay = s.post(
                "https://tkglobal.melon.com/reservation/ajax/payInitForm.htm?procMode=R",
                data=pay_init_payload,
                headers={**h_post2, "Referer": "https://tkglobal.melon.com/reservation/popup/stepDelvy.htm"},
                timeout=15,
            )
            with open("runtime_payInitForm.html", "w", encoding="utf-8") as f:
                f.write(r_pay.text)
            print(f"  status={r_pay.status_code}, body_length={len(r_pay.text)}")
            payment_targets = extract_payment_targets_from_html(r_pay.text)
            if payment_targets:
                print("  payment targets:")
                for target in payment_targets[:10]:
                    print(f"    - {target}")
            else:
                print("  no direct payment URL extracted; see runtime_payInitForm.html")
        else:
            print("  non-card payment flow, no payInitForm step needed")
    else:
        print("\n  FAIL save.json rejected the order")

    print("\n" + "=" * 60)
    s.close()


if __name__ == "__main__":
    main()
