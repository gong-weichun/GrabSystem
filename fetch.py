import json
import random
import time
import re
from HttpClientHelper import TLSHttpClient
from SolveCaptcha import ocr_from_base64
import global_resources
from ui import UiWindow

def fetch_thread():
    SeatType = 0

    TelephoneNum = "15864230665"
    clientIp = "36.232.72.58"
    ifNeedSelectArea = False
    floorNo = ""
    floorName = ""
    areaNo = ""
    areaName = ""
    sntv = ""
    scheduleNo = "100001"
    sellTypeCode = "ST0001"
    pocCode = "SC0002"
    trafficCtrlYn = ""
    prodKey = ""
    perfMainName = ""
    placeId = ""
    modifyDate = ""
    perfTypeCode = ""
    prodTypeCode = ""
    perfDay = ""
    perfDate = ""
    perfStartDay = ""
    flplanTypeCode = ""
    scheduleTypeCode = ""
    blockId = ""
    seatGradeNo = ""
    seatGradeName = ""
    seatTypeCode = ""
    limitVolume = 0
    seatId = ""
    encryptedSeatIds = ""
    blockTypeCode = ""
    rsrvStep = ""
    rsrvSeq = ""
    zamEnabled = ""
    zamKey = ""
    stvn_view_list = ""
    mapClickYn = ""
    priceNo = ""
    rsrvVolume = ""
    excuteState = 0
    strRequestUrl = ""  # 请求地址
    strRequestParameter = ""  # 请求参数
    callBack = ""  # 响应回调字符串
    strResponseHtml = ""  # 发起请求后返回的响应字符串
    dicResponseResult = {}  # 发起请求后响应字典结果
    nflActId = ""  # 购票后返回的一个ID，用于后续发起排队请求的入参
    strQueCode = ""  # 发起排队请求后返回的编码
    strQueKey = ""  # 发起排队请求后返回的key值
    strCaptchaKey = ""  # 验证码提交后返回的key值
    requestInterval = 500  # 请求间隔
    waitNum = 0

    client = TLSHttpClient()
    while True:
        try:
            MemberKey = global_resources.MemberKey
            EventID = global_resources.EventID
            scheduleNo = global_resources.ScheduleNo
            if global_resources.blStartGrab:
                LogMessage("开始...")
                if excuteState == 0:
                    callBack = "scheduleList8"
                    strRequestUrl = "https://tkglobal.melon.com/tktapi/glb/product/prodKey.json"
                    strRequestParameter = "?callback=" + callBack + "&prodId=" + EventID + "&scheduleNo=" + scheduleNo + "&v=1&_=" + str(
                        int(round(time.time() * 1000)))
                    requestResponse = client.get(strRequestUrl + strRequestParameter)
                    if requestResponse.status_code == 200:
                        strResponseHtml = requestResponse.text
                        dicResponseResult = json.loads( process_jsonp_response_robust(strResponseHtml, "/**/" + callBack))
                        if "code" in dicResponseResult:
                            if dicResponseResult["code"] == "0000":
                                nflActId = dicResponseResult["nflActId"]
                                trafficCtrlYn = dicResponseResult["trafficCtrlYn"]
                                prodKey = dicResponseResult["key"]
                                excuteState = 1
                            else:
                                LogMessage("等待开放售卖中...")
                                time.sleep(1)
                    else:
                        time.sleep(1)
                elif excuteState == 1:
                    if trafficCtrlYn.upper() == "Y":
                        if strQueCode == "":
                            strRequestUrl = "https://zam.melon.com/ts.wseq?opcode=5101&nfid=0&prefix=NetFunnel.gRtype=5101;&ttl=2&sid=service_1&aid=" + nflActId + "&js=yes&user_data=" + MemberKey + "&" + str(
                                int(round(time.time() * 1000)))
                            requestResponse = client.get(strRequestUrl)
                            if requestResponse.status_code == 200:
                                strResponseHtml = requestResponse.text
                                arr1 = strResponseHtml.split(";")
                                arr2 = arr1[1].split("&")
                                arr3 = arr2[0].split(":")
                                strQueKey = arr3[2].replace("key=", "")
                                waitNum = int(arr2[1].replace("nwait=", ""))
                                if waitNum > 0:
                                    strQueCode = "5002"
                                elif waitNum == 0:
                                    strQueCode = ""
                                    excuteState = 2
                        elif (strQueCode == "5002"):  # 返回的编码是5002，则需要排队，后续重复发起排队查询请求
                            strRequestUrl = "https://zam.melon.com/ts.wseq?opcode=5002&key=" + strQueKey + "&nfid=0&prefix=NetFunnel.gRtype=5002;&ttl=2&sid=service_1&aid=" + nflActId + "&user_data=" + MemberKey + "&js=yes&" + str(
                                int(round(time.time() * 1000)))
                            requestResponse = client.get(strRequestUrl)
                            LogMessage("get请求返回状态：" + requestResponse.status_code)
                            if (requestResponse.status_code == 200):
                                strResponseHtml = requestResponse.text
                                LogMessage(strResponseHtml)
                                arr1 = strResponseHtml.split(";")
                                arr2 = arr1[1].split("&")
                                arr3 = arr2[0].split(":")
                                strQueKey = arr3[2].replace("key=", "")
                                waitNum = int(arr2[1].replace("nwait=", ""))
                                if (waitNum == 0):
                                    strQueCode = ""
                                    excuteState += 1
                                    LogMessage("结束排队，进入下一状态")
                                if (waitNum > 1000):
                                    strQueCode = "5002"
                                    LogMessage("正在排队，前方排队人数为：" + str(waitNum))
                                    time.sleep(1)
                            else:
                                time.sleep(0.05)
                    else:
                        strQueCode = ""
                        excuteState = 2
                elif excuteState == 2:  # 处理验证码
                    if strCaptchaKey == "":  # 第一次请求时要处理验证码
                        strRequestUrl = "https://tkglobal.melon.com/reservation/ajax/captChaImage.json?prodId=" + EventID + "&scheduleNo=" + scheduleNo + "&t=" + str(
                            int(round(time.time() * 1000)))
                        requestResponse = client.get(strRequestUrl)
                        if requestResponse.status_code == 200:
                            strResponseHtml = requestResponse.text
                            dicResponseResult = json.loads(strResponseHtml)
                            LogMessage(strResponseHtml)
                            CaptchaResult = ""
                            if "CAPTIMAGE" in dicResponseResult:
                                CaptchaData = dicResponseResult["CAPTDATA"]
                                Base64Code = dicResponseResult["CAPTIMAGE"]
                                CaptchaResult = ocr_from_base64(Base64Code)
                                strRequestUrl = "https://tkglobal.melon.com/reservation/ajax/checkCaptcha.json"
                                strRequestParameter = "userCaptStr=" + CaptchaResult + "&chkcapt=" + CaptchaData + "&prodId=" + EventID + "&scheduleNo=" + scheduleNo + "&pocCode=" + pocCode + "&sellTypeCode=" + sellTypeCode
                                requestResponse = client.post(strRequestUrl, strRequestParameter)
                                if (requestResponse.status_code == 200):
                                    strResponseHtml = requestResponse.text
                                    dicResponseResult = json.loads(strResponseHtml)
                                    if "DATA" in dicResponseResult:
                                        strCaptchaKey = dicResponseResult["DATA"]
                                        if strCaptchaKey != "":
                                            excuteState = 3
                                    else:
                                        LogMessage("验证码不通过，再次尝试")
                                        time.sleep(1)
                                    LogMessage(strResponseHtml)
                        else:
                            LogMessage("请求失败，返回状态：" + requestResponse.status_code + "，再次尝试")
                            time.sleep(1)

                elif excuteState == 3:  # 获得产品信息
                    strRequestUrl = "https://tkglobal.melon.com/tktapi/product/informProdSch.json?v=1"
                    strRequestParameter = "prodId=" + EventID + "&pocCode=" + pocCode + "&scheduleNo=" + scheduleNo + "&sellTypeCode=" + sellTypeCode + "&sellCondNo=&perfDate="
                    requestResponse = client.post(strRequestUrl, strRequestParameter)
                    if requestResponse.status_code == 200:
                        strResponseHtml = requestResponse.text

                        if "prodInform" in strResponseHtml:
                            dicResponseResult = json.loads(strResponseHtml)
                            perfMainName = dicResponseResult.perfMainName
                            prodTypeCode = dicResponseResult.prodTypeCode
                            trafficCtrlYn = dicResponseResult.trafficCtrlYn
                            perfTypeCode = dicResponseResult.perfTypeCode
                            perfStartDay = dicResponseResult.perfStartDay
                            perfDay = perfStartDay
                            perfDate = perfStartDay
                            flplanTypeCode = str(dicResponseResult.flplanTypeCode)
                            scheduleTypeCode = dicResponseResult.scheduleTypeCode
                            limitVolume = dicResponseResult.limitVolume
                            LogMessage(strResponseHtml)
                            excuteState = 4
                    else:
                        LogMessage("请求失败，返回状态：" + requestResponse.status_code + "，再次尝试")
                        time.sleep(1)
                elif excuteState == 4:  # 获得限制信息，如最多买多少票
                    strRequestUrl = "https://tkglobal.melon.com/tktapi/glb/product/informLimit.json"
                    strRequestParameter = "v=1&prodId=" + EventID + "&pocCode=" + pocCode + "&scheduleNo=" + scheduleNo + "&sellTypeCode=" + sellTypeCode
                    requestResponse = client.post(strRequestUrl, strRequestParameter)
                    LogMessage("请求返回状态：" + requestResponse.status_code)
                    if requestResponse.status_code == 200:
                        strResponseHtml = requestResponse.text
                        LogMessage(strResponseHtml)
                        dicResponseResult = json.loads(strResponseHtml)
                        if "code" in dicResponseResult:
                            if (dicResponseResult["code"] == "0000"):
                                excuteState = 5
                    else:
                        LogMessage("请求失败，返回状态：" + requestResponse.status_code + "，再次尝试")
                        time.sleep(1)
                elif excuteState == 5:  # 获得产品售卖状态，应该在这个位置判断后续要走有区域流程还是无区域流程
                    callBack = "getValiProductScheduleCallBack"
                    strRequestUrl = "https://tkglobal.melon.com/tktapi_poc/performance/getProdSellState.json?v=1&callback=" + callBack
                    strRequestParameter = "prodId=" + EventID + "&scheduleNo=" + scheduleNo
                    requestResponse = client.post(strRequestUrl, strRequestParameter)
                    LogMessage("请求返回状态：" + requestResponse.status_code)

                    if (requestResponse.status_code == 200):
                        strResponseHtml = requestResponse.text
                        LogMessage(strResponseHtml)
                        jsonResult = process_jsonp_response_robust(strResponseHtml, "/**/" + callBack)
                        excuteState = 6
                    else:
                        LogMessage("请求失败")
                elif excuteState == 6:
                    if SeatType == 0:  # 选区域再选座位
                        callBack = "getBlockGradeSeatCountCallBack"
                        strRequestUrl = "https://tkglobal.melon.com/tktapi/glb/product/summary.json?v=1&callback=" + callBack
                        strRequestParameter = "chkcapt=" + strCaptchaKey + "&prodId=" + EventID
                        requestResponse = client.get(strRequestUrl + strRequestParameter)
                        time.sleep(random.uniform(requestInterval, requestInterval + 100) / 1000)
                        LogMessage("get返回状态：" + requestResponse.status_code)

                        if (requestResponse.status_code == 200):
                            strResponseHtml = requestResponse.text
                            LogMessage(strResponseHtml)
                            jsonResult = process_jsonp_response_robust(strResponseHtml, "/**/" + callBack)
                            callBack = "getBlockGradeSeatMapCallBack"
                            strRequestUrl = "https://tkglobal.melon.com/tktapi/glb/product/getAreaMap.json?v=1&callback=" + callBack
                            strRequestParameter = "chkcapt=" + strCaptchaKey + "&prodId=" + EventID
                            requestResponse = client.get(strRequestUrl + strRequestParameter)
                            time.sleep(random.uniform(requestInterval, requestInterval + 100) / 1000)
                            LogMessage("get返回状态：" + requestResponse.status_code)

                            if (requestResponse.status_code == 200):
                                strResponseHtml = requestResponse.text
                                LogMessage(strResponseHtml)

                                jsonResult = process_jsonp_response_robust(strResponseHtml, "/**/" + callBack)

                                callBack = "getBlockSummaryCountCallBack"
                                strRequestUrl = "https://tkglobal.melon.com/tktapi/product/block/summary.json?v=1&callback=" + callBack
                                strRequestParameter = "prodId=" + EventID + "&pocCode=" + pocCode + "&scheduleNo=" + scheduleNo + "&seatGradeNo="
                                requestResponse = client.post(strRequestUrl, strRequestParameter)
                                time.sleep(random.uniform(requestInterval, requestInterval + 100) / 1000)
                                LogMessage("请求返回状态：" + requestResponse.status_code)

                                if (requestResponse.status_code == 200):
                                    strResponseHtml = requestResponse.text
                                    LogMessage(strResponseHtml)

                                    jsonResult = process_jsonp_response_robust(strResponseHtml, "/**/" + callBack)

                                    callBack = "getSeatListCallBack"
                                    strRequestUrl = "https://tkglobal.melon.com/tktapi/product/seat/seatMapList.json?v=1&callback=" + callBack
                                    strRequestParameter = "prodId=" + EventID + "&scheduleNo=" + scheduleNo + "&blockId=" + blockId + "&pocCode=" + pocCode
                                    requestResponse = client.post(strRequestUrl, strRequestParameter)
                                    time.sleep(random.uniform(requestInterval, requestInterval + 100) / 1000)
                                    LogMessage("post返回状态：" + requestResponse.status_code)
                                    if (requestResponse.status_code == 200):
                                        strResponseHtml = requestResponse.text
                                        LogMessage(strResponseHtml)
                                        jsonResult = process_jsonp_response_robust(strResponseHtml, "/**/" + callBack)
                                        seatMapListHelper = json.loads(jsonResult)  # 在这里获得座位信息
                                        if (seatMapListHelper.seatData != None):
                                            seatTypeCode = seatMapListHelper.seatData.da.sb[0].sbt
                                            seatId = ""
                                            for itemSt in seatMapListHelper.seatData.st:
                                                if (seatId == ""):
                                                    for itemSs in itemSt.ss:  # sid表示座位号，sn、snm表示座位的索引，应该是数值越小越靠前
                                                        if itemSs.sid != None:  # sid为null表示座位被选走
                                                            seatId = itemSs.sid
                                                            break
                                                        else:
                                                            excuteState = 7
                                                        break
                                    else:
                                        LogMessage("post请求失败")
                                else:
                                    LogMessage("请求失败")
                            else:
                                LogMessage("get请求失败")
                        else:
                            LogMessage("get请求失败")
                    elif SeatType == 1:
                        callBack = "getSeatListCallBack"
                        strRequestUrl = "https://tkglobal.melon.com/tktapi/product/seat/seatMapList.json?v=1&callback=" + callBack
                        strRequestParameter = "prodId=" + EventID + "&scheduleNo=" + scheduleNo + "&blockId=&pocCode=" + pocCode + "&corpCodeNo="
                        requestResponse = client.post(strRequestUrl, strRequestParameter)
                        time.sleep(random.uniform(requestInterval, requestInterval + 100) / 1000)
                        LogMessage("post返回状态：" + requestResponse.status_code)

                        if (requestResponse.status_code == 200):
                            strResponseHtml = requestResponse.text
                            LogMessage(strResponseHtml)

                            jsonResult = process_jsonp_response_robust(strResponseHtml, "/**/" + callBack)
                            seatMapListHelper = json.loads(jsonResult)  # 在这里获得座位信息
                            if (seatMapListHelper.seatData != None):
                                seatTypeCode = seatMapListHelper.seatData.da.sb[0].sbt
                                seatId = ""
                                for itemSt in seatMapListHelper.seatData.st:
                                    if (seatId == ""):
                                        for itemSs in itemSt.ss:  # sid表示座位号，sn、snm表示座位的索引，应该是数值越小越靠前
                                            if (itemSs.sid != None):  # sid为null表示座位被选走
                                                seatId = itemSs.sid
                                                break
                                            else:
                                                callBack = "getBlockGradeSeatCountCallBack"
                                                strRequestUrl = "https://tkglobal.melon.com/tktapi/glb/product/summary.json?v=1&callback=" + callBack
                                                strRequestParameter = "chkcapt=" + strCaptchaKey + "&prodId=" + EventID
                                                requestResponse = client.get(strRequestUrl + strRequestParameter)
                                                time.sleep(
                                                    random.uniform(requestInterval, requestInterval + 100) / 1000)
                                                LogMessage("get返回状态：" + requestResponse.status_code)
                                                if (requestResponse.status_code == 200):
                                                    strResponseHtml = requestResponse.text
                                                    LogMessage(strResponseHtml)
                                                    jsonResult = process_jsonp_response_robust(strResponseHtml,
                                                                                               "/**/" + callBack)
                                                    excuteState = 7
                                                else:
                                                    LogMessage("get请求失败")
                        else:
                            LogMessage("post请求失败")
                elif excuteState == 7:
                    callBack = "jQuery3600".join(random.choices("0123456789", k=13)) + "_" + str(
                        int(round(time.time() * 1000)))
                    strRequestUrl = "https://tkglobal.melon.com/tktapi/glb/reservation/prodlimit.json?v=1&callback=" + callBack
                    strRequestParameter = "langCd=EN&prodId=" + EventID + "&pocCode=" + pocCode + "&perfTypeCode=" + perfTypeCode \
                                          + "&perfDate=" + perfDay + "&scheduleNo=" + scheduleNo + "&sellTypeCode=" + sellTypeCode \
                                          + "&sellCondNo=&perfMainName=" + perfMainName + "&seatGradeNo=" + seatGradeNo + "&seatGradeName=" + seatGradeName + "&blockId=" + blockId + "&sntv=" + sntv + "&blockTypeCode=" + blockTypeCode + "&floorNo=" + floorNo + "&floorName=" + floorName \
                                          + "&areaNo=" + areaNo + "&areaName=" + areaName + "&prodTypeCode=" + prodTypeCode + "&flplanTypeCode=" + flplanTypeCode + "&scheduleTypeCode=" + scheduleTypeCode + "&seatTypeCode=" + seatTypeCode \
                                          + "&jType=I&cardGroupId=&cardBpId=&cardMid=&rsrvStep=" + rsrvStep + "&zamEnabled=" + zamEnabled + "&zamKey=" + zamKey + "&trafficCtrlYn=" + trafficCtrlYn \
                                          + "&netfunnel_key=&stvn_view_list=" + stvn_view_list + "&mapClickYn=" + mapClickYn + "&seatId=" + seatId + "&clipSeatId=&chkcapt="
                    requestResponse = client.post(strRequestUrl, strRequestParameter)
                    LogMessage("返回状态：" + requestResponse.status_code)
                    if (requestResponse.status_code == 200):
                        strResponseHtml = requestResponse.text
                        LogMessage(strResponseHtml)
                        jsonResult = process_jsonp_response_robust(strResponseHtml, "/**/" + callBack)
                        dicResponseResult = json.loads(jsonResult)
                        if ("result" in dicResponseResult & dicResponseResult["result"] == "0000"):
                            encryptedSeatIds = dicResponseResult["encryptedSeatIds"]
                            excuteState = 8
                    else:
                        LogMessage("请求失败")
                elif excuteState == 8:
                    callBack = "jQuery3600".join(random.choices("0123456789", k=13)) + "_" + str(
                        int(round(time.time() * 1000)))
                    strRequestUrl = "https://tkglobal.melon.com/tktapi/glb/product/tickettype.json?v=1&callback=jQuery3600" + callBack
                    strRequestParameter = "langCd=EN&prodId=" + EventID + "&pocCode=" + pocCode + "&perfTypeCode=" + perfTypeCode + "&perfDate=" \
                                          + perfDate + "&scheduleNo=" + scheduleNo + "&sellTypeCode=" + sellTypeCode + "&sellCondNo=&perfMainName="
                    + perfMainName + "&seatGradeNo=&seatGradeName=&blockId=" + blockId + "&sntv=FLOOR%2CON&blockTypeCode=&floorNo=FLOOR" + \
                    "&floorName=%EC%B8%B5&areaNo=ON&areaName=%EA%B5%AC%EC%97%AD&prodTypeCode=" + prodTypeCode + "&flplanTypeCode=" \
                    + flplanTypeCode + "&scheduleTypeCode=" + scheduleTypeCode + "&seatTypeCode=" + seatTypeCode + "&jType=I&cardGroupId=&cardBpId=" + \
                    "&cardMid=&rsrvStep=" + rsrvStep + "&zamEnabled=0&zamKey=&trafficCtrlYn=" + trafficCtrlYn + "&netfunnel_key=" + \
                    "&stvn_view_list=" + stvn_view_list \
                    + "&mapClickYn=Y&seatId=" + seatId  # 多个座位的话可拼接， & seatId = 404_776
                    requestResponse = client.post(strRequestUrl, strRequestParameter)
                    if (requestResponse.status_code == 200):
                        strResponseHtml = requestResponse.text
                        dicResponseResult = json.loads(strResponseHtml)
                        if "encryptedSeatIds" in dicResponseResult:
                            strCaptchaKey = dicResponseResult["DATA"]
                            if strCaptchaKey != "":
                                excuteState = 9
                        LogMessage(strResponseHtml)
                    else:
                        LogMessage("请求失败")
                elif excuteState == 9:  # 选择价格pricelimit
                    strRequestUrl = "https://tkglobal.melon.com/tktapi/glb/reservation/pricelimit.json?v=1&callback=jQuery3600".join(
                        random.choices("0123456789", k=13)) + "_" + str(int(round(time.time() * 1000)))
                    strRequestParameter = "langCd=EN&prodId=" + EventID + "&pocCode=" + pocCode + "&perfTypeCode=" + perfTypeCode + "&perfDate=" + perfDate + "&scheduleNo=" \
                                          + scheduleNo + "&sellTypeCode=" + sellTypeCode + "&sellCondNo=&perfMainName=" + perfMainName + "&seatGradeNo=&seatGradeName=" + \
                                          "&blockId=" + blockId + "&sntv=" + sntv + "&blockTypeCode=" + blockTypeCode + "&floorNo=" + floorNo + "&floorName=" + floorName + "&areaNo=" + areaNo + "&areaName=" + areaName + "&prodTypeCode=" \
                                          + prodTypeCode + "&flplanTypeCode=" + flplanTypeCode + "&scheduleTypeCode=" + scheduleTypeCode + "&seatTypeCode=" + seatTypeCode \
                                          + "&jType=I&cardGroupId=&cardBpId=&cardMid=&rsrvStep=" + rsrvStep + "&zamEnabled=" + zamEnabled + "&zamKey=" + zamKey + "&trafficCtrlYn=" + trafficCtrlYn + "&netfunnel_key=" + \
                                          "&stvn_view_list=" + stvn_view_list + "&mapClickYn=" + mapClickYn + "&priceNo=" + priceNo + "&rsrvVolume=" + rsrvVolume + "&chkcapt=" + strCaptchaKey
                    requestResponse = client.post(strRequestUrl, strRequestParameter)
                    if (requestResponse.status_code == 200):
                        strResponseHtml = requestResponse.text
                        dicResponseResult = json.loads(strResponseHtml)
                        if "encryptedSeatIds" in dicResponseResult:
                            encryptedSeatIds = dicResponseResult["encryptedSeatIds"]
                            if (encryptedSeatIds != ""):
                                excuteState = 10
                        LogMessage(strResponseHtml)
                    else:
                        LogMessage("请求失败")
                elif excuteState == 10:  # 提交支付delivery
                    strRequestUrl = "https://tkglobal.melon.com/tktapi/glb/product/delivery.json?v=1&callback=jQuery3600".join(
                        random.choices("0123456789", k=13)) + "_" + str(int(round(time.time() * 1000)))
                    strRequestParameter = "langCd=EN&prodId=" + EventID + "&pocCode=" + pocCode + "&perfTypeCode=" + perfTypeCode + "&perfDate=" + perfDate + "&scheduleNo=" + scheduleNo \
                                          + "&sellTypeCode=" + sellTypeCode + "&sellCondNo=&perfMainName=" + perfMainName + "&seatGradeNo=&seatGradeName=&blockId=" + blockId \
                                          + "&sntv=" + sntv + "&blockTypeCode=" + blockTypeCode + "&floorNo=" + floorNo + "&floorName=" + floorName + "&areaNo=" + areaNo + "&areaName=" + areaName + "&prodTypeCode=" + prodTypeCode \
                                          + "&flplanTypeCode=" + flplanTypeCode + "&scheduleTypeCode=" + scheduleTypeCode + "&seatTypeCode=" + seatTypeCode \
                                          + "&jType=I&cardGroupId=&cardBpId=&cardMid=&rsrvStep=" + rsrvStep + "&zamEnabled=" + zamEnabled + "&zamKey=" + zamKey + "&trafficCtrlYn=" + trafficCtrlYn + "&netfunnel_key=" + \
                                          "&stvn_view_list=" + stvn_view_list + "&mapClickYn=" + mapClickYn
                    requestResponse = client.post(strRequestUrl, strRequestParameter)
                    if (requestResponse.status_code == 200):
                        strResponseHtml = requestResponse.text
                        dicResponseResult = json.loads(strResponseHtml)
                        LogMessage(strResponseHtml)
                        excuteState = 11
                    else:
                        LogMessage("请求失败")
                elif excuteState == 11:
                    strRequestUrl = "https://tkglobal.melon.com/reservation/ajax/payInitForm.htm?procMode=R"
                    strRequestParameter = "flplanTypeCode=" + flplanTypeCode + "&code=0000&seatInfoListWithPriceType=%5B%7B%22priceNo%22%3A10067%2C%22seatId%22%3A%22404_847%22%2C%22gradeNm%22%3A%22%EC%9D%BC%EB%B0%98%EC%84%9D(%EC%8A%A4%ED%83%A0%EB%94%A9)%22%2C%22seatNm%22%3A%22FLOOR+%EC%B8%B5+ON+%EA%B5%AC%EC%97%AD+689+%EB%B2%88+%22%2C%22basePrice%22%3A154000%2C%22priceName%22%3A%22%EA%B8%B0%EB%B3%B8%EA%B0%80%22%2C%22sejongPriceCode%22%3Anull%7D%2C%7B%22priceNo%22%3A10067%2C%22seatId%22%3A%22404_776%22%2C%22gradeNm%22%3A%22%EC%9D%BC%EB%B0%98%EC%84%9D(%EC%8A%A4%ED%83%A0%EB%94%A9)%22%2C%22seatNm%22%3A%22FLOOR+%EC%B8%B5+ON+%EA%B5%AC%EC%97%AD+619+%EB%B2%88+%22%2C%22basePrice%22%3A154000%2C%22priceName%22%3A%22%EA%B8%B0%EB%B3%B8%EA%B0%80%22%2C%22sejongPriceCode%22%3Anull%7D%5D" + \
                                          "&cardCode=FOREIGN_CHINABANK&jtype=I&eType=&cust_ip=34.96.1.134&prodId=" + EventID + "&kakaoPayType=&userName=weichun+gong&payAmt=322000" + \
                                          "&perfMainName=" + perfMainName \
                                          + "&midOptionKey=%EC%98%A8%EB%9D%BC%EC%9D%B8_%ED%95%B4%EC%99%B8_%EC%9D%B8%EC%A6%9D_%EC%9D%BC%EB%B0%98&staticDomain=&httpsDomain=&quota=00" + \
                                          "&tel=" + TelephoneNum + "&rsrvSeq=" + rsrvSeq + "&payMethodCode=AP0012&httpDomain=&card_pay_method=GLB"
                    requestResponse = client.post(strRequestUrl, strRequestParameter)
                    if (requestResponse.status_code == 200):
                        strResponseHtml = requestResponse.text
                        dicResponseResult = json.loads(strResponseHtml)
                        if "DATA" in dicResponseResult:
                            strCaptchaKey = dicResponseResult["DATA"]
                            if strCaptchaKey != "":
                                excuteState = 12
                        LogMessage(strResponseHtml)
                    else:
                        LogMessage("请求失败")
                elif excuteState == 12:  # 发起支付，准备输入卡号
                    strRequestUrl = "https://stdpay.inicis.com/jsApi/union/requestVerify"
                    strRequestParameter = "cardCode=26&cardQuota=00&Ocbcard1=&Ocbcard2=&Ocbcard3=&Ocbcard4=&plan=lpointType2&chkLpointUse=on&lCardNo1=" + \
                                          "&lCardNo2=&lCardNo3=&lCardNo4=&lCardPw=&usePoint=&cardCodesNormal=21%2C22%2C23%2C24%2C25&cardCodesVisa3dDacom=12%2C14%2C41%2C32%2C53%2C48%2C04" + \
                                          "&mallPointList=&cardCodesIsp=11%2C06%2C51%2C44%2C62%2C95%2C33%2C99&popupFlag=0&cardSelectVisa3d=21%3A22%3A23&cardSelectNormal=25&nointwithprice=" + \
                                          "&slimNoInterestList=&cardSelectUnion=26&cardMaxQuotaList=01%3D12%3A12%2602%3D12%3A12%2603%3D12%3A12%2604%3D24%3A12%2606%3D12%3A12%2611%3D12%3A12%2612%3D12%3A12%2614%3D12%3A12%2634%3D12%3A12%2641%3D12%3A12" + \
                                          "&selectPopup=0&cardNoInterestEvent=&cardCodesVisa3dIlk=11%2C06%2C51%2C44%2C95%2C33&cardSelectIsp=&cardNoInterestEventNew=&CARD_Point=0&visa3dRequest=&visa3dResponse=" + \
                                          "&ocbRequestdata=&ocbSave_flg=false&kbAppRequest=&kbAppResponse=&KBAPP=&couponInfo=&couponGroup=&checkNoInt=&escrowCardData=&payPopup=0&NoInterestQuotaList=%5B%5D" + \
                                          "&EventNoInterestQuotaList=%5B%5D&installmentPrice=50000&cardPointList=&cardPointDetailList=&q5CardPointList=&diffCardPointList=" + \
                                          "&selectNointCardList=01%2C02%2C03%2C11%2C13%2C21%2C22%2C23%2C24%2C25%2C26%2C27%2C31%2C32%2C33%2C35%2C36%2C37%2C38%2C39%2C40%2C41%2C42%2C43%2C44%2C45%2C46%2C47%2C48%2C49%2C51%2C52%2C53%2C54%2C55%2C56%2C62%2C71%2C81%2C88%2C95%2C99" + \
                                          "&viewChangeCardList=&sspRequest=&sspResponse=&paycoResponse=&SSG_PAY_REQ=&SSG_PAY_RES=&lpTotalPrice=&lpCardPrice=&lpoint=&lpointAll=&lpointCdcd=cardCode20&cryptLpInfo=" + \
                                          "&lpUse=&umpUse=0&card_customized_msg=&interest_min_quota=&interestEventChk=1&USE_KCARE=&PR_KCARE=&CNF_KCARE=0&payCount=0&hdAmexYn=&hdAmexGrade=&CARD_VoucherCode=" + \
                                          "&escrowFullData=&uniResponse=&oriGoodsname=2025+KAI+SOLO+CONCERT+TOUR+%E3%80%88KAION%E3%80%89+ENCORE+IN+SEOUL&escrowTid=&fds_ukey=b94d17e9-3bf9-499c-8da7-142a9860613c" + \
                                          "&billRegNo=&logo_url=&logo_2nd=https%3A%2F%2Fstdux.inicis.com%2Fstdpay%2Fimg%2Fnew_logo04.png&quotaNointYn=&cardnumreturn=&returnFlag=&NAVR_SP_ORDER_USER_ID=&price=161000" + \
                                          "&gopaymethod=card&p_subcnt=&verificationYN=Y&payViewType=overlay&ini_PAYSHOT_KEY=&quotabase=0%3A2%3A3%3A4%3A5%3A6%3A7%3A8%3A9%3A10%3A11%3A12&ini_SSGPAY_PRODUCTCNT=1" + \
                                          "&buyertel=0000000000&boolView=&fds_wdata=V%2BRB%2BAI6aGU5xcYDWDkuex6hNoJlC0AhOAcTqGQGyawnUcrBpMhnjh0jZG4mSQntyRgElwCzGhGFc9U0V%2BnYlkYA4AdoDUGc0WsvWu52395zu4qCnf%2BoGriMibbHhNMAa5XcgpILqKqhxq5PK9hd4qLEem%2FibVXNtRD8BnNb1Lr51cIV%2BlmwO7dvJDQ0PB5b1%2F%2FHJpojv0AP4DG1FM21LFohxMaKJWzqDrPxBL1%2BUDoEwWz68YmUPLjVZm1mbOpMBaV3tfM%2BKx57zDrrTbJ7aGzhplsBnsbUhuofx0cTZOVkOVv8eqqD5%2FpeKTowgE5rUVIAjqqCaP8n8TfX9gKh1ZPpQ4Oqnh4hP0M3GxZsIX9TfBpdWw3AMnIuT56tzMBEvugW4nJ%2FpXoaiO3S63YtLD%2Fy0UDRcKxIBiWLqvIy%2FboOltbpNWaGOAohIuqwkpu4mOcH1Q%2FRv5pg%2FU29Hb8p9zfzT1tFq1taQeTbKmp0SL5Tv9x7Ek7yX8%2BJSwwl%2F%2Bd2Kj58i3ulk87ZyYEslZMAcJ6D%2FsRZJ6C3E9BaxAAf1e3lFwzDsznCx%2FOKgK2pYi%2B4s6KXkTj5ihsWlLSFCLI8Gl82FXQTg5dGj%2BkObxIVLSj%2FXJj%2F%2FCTIAm7X%2BNkjLJ%2FMPYx8WLex350s2BNmV95OQRomsT9PHMoXjK20qkPrDtX8ImipESJrE%2B0p93udKwGN%2BBl5aNenqqWTXZh%2Behbeq2BSvkS9E7hjrvTc0APzFG8S%2Fpv7kWlwPh1AP6xdko3HF6daVjTRl%2Bf5xKKWIbA9Zew0NVKzJPlILAurfgmT6RyE6HgrlevUrgJmjfvW9%2BwcMvoUccNGeX73zDd24qItBYrYPoEftVtNgstL4xN4GQ3dOHMHTYaIWpm8bc6kD%2BLC7b8L2CbMH5WjPzWvPIiLQlyLTBoTT04AfBf%2Fm3vIaGBmaYnyjgLAhXfot%2BVeEno4qQkLtHYD%2BKu%2BcJJ2SuaWlQSiZf413q2rL7cnS6vT%2FoG1iyxmon9qrLJUduXmBs9YkOpHialKGhX99%2FTvbPWpwtRK%2FcVNPtGRYp4oBWG2N5eYZ0y4i%2Br%2FlsV4Bmro4k6%2B9iEIxyu6ZObFCnnQTOlOkR9Q1%2F7OzYy3sAAjB2pSNJ%2FcmNrjJ44NCvl8CJwkbvzhkNoRAFfMhNz0sJYfb8i%2BN5xcsl8ReJTDoQGIAcve6xNTOHk5QOMokbnrdIqvynleSimsZvaw%2Fn%2Bp8XNB8ynSxtJ0hUMfqIzyitV7zt260qY1HFXVPrk0slF7Xmj%2BOuT1ZbU92e8iGCmD7N3tEAz0rFCYamOopkwH" + \
                                          "&voucherGokrCnt=&acceptmethod=SKIN(ORIGINAL)%3Abelow1000%3Aini_onlycardcode(26)%3Apopreturn&ini_fullbanner_url=&merchantDeadLine=&taxfree=&ini_fullbanner_url3=&ini_fullbanner_url2=" + \
                                          "&rentalCompPhone=&subCompanyAddr=&site_id=&uway_logo_url=&goodsoid=&buyeremail=&aid=ticketon0520250813004352969_3BCF3BD47407&charset=UTF-8&ini_safetykey_reg=" + \
                                          "&useragent=Chrome_Win10+%5B+mozilla%2F5.0+(windows+nt+10.0%3B+win64%3B+x64)+applewebkit%2F537.36+(khtml%2C+like+gecko)+chrome%2F138.0.0.0+safari%2F537.36+%5D&mid=ticketon05&pgIp=" + \
                                          "&fds_sno=031611&languageView=en&limitTimeAlertTime=10&basicInfo=UaTqX9k8kZm4TPKeQzM8ADlfNhNHE%2Bkg6J4FYnbLUgH1t212F8fHw%2F%2FIEFEbUg1W%0D%0ApW%2FdqBbGFbW7CFA7lEJ1d7Dg%2Bysrov8FUBR9vFxa%2BdB5mToWLLDvOr1ekqOAteDb%0D%0AK5RqP42PjuzJcqaG8YYyrispkFqUCynAPj3XFB1qnVwKhKIngzjLsvWotcSrYgvZ%0D%0A7GR7Wd4lqnl8LD9%2B47gyMDY5lDlUKNz05OC2JRJ%2BWObpEwvmRjQ7zRwtmd69qzlO%0D%0A%2FW0%2BovT%2F8IHjGL5miLDMQCQEWoNd%2BeJLp6cpQInRdTzV2PPjX4oqOInbQibfstyG%0D%0ASme80wV5VoYdUg5QqgXcPE%2FvRf%2F27sA0Pt1mfhn4oiZGgpKtRj6R3yUi%2BqDIECtr%0D%0AVBY9DnQFOuQNFfVmNZZXH6xQqIB1X%2BxIrYM7CpBIdUczgqD4Uel7i1gkHydQxiAo%0D%0Ahr3I%2BSw68pVrAQAL8kybjGE%2BkCKnMbhFbqnZ5yCnozfL5zv%2BGvK4crqjKgl3NSfK%0D%0ApYEF6xcI%2FqO%2B2leASIm2zvnyOpFdTw%2Frn6tuUXvZWa%2FvpGlGkjslf5X1GH4pGHjo%0D%0AyOBLsAsH%2BW%2FoB9E8GbC7R5AJw48iFC9ikI7zhr7oiyj33uFXeUO%2FQGrdxO9cwy33%0D%0ArnSPIaXtszDq0Y%2Bt2SAqnb3URTzCY%2BmnghJK%2FC9yfuMIKPzk2FEDLxqdvJuFW3AR%0D%0Aj1IPavBKBnYqUghkGgdaW5OiOwu1pdnqnT8y3qAU4%2FtXP1q%2F7%2Bu%2F%2FVUpnQndhmSi%0D%0AygdG99%2BiLZPT8uNn1V80XV%2BefWamQjM6Apdgr7ZThDfPGfPRKle7FPnIodU8i8UZ%0D%0A9UEQ%2B9BoRibgiAYbzOwwGERJhUFWUC%2FA1ASdmg2q2EsqWgzBknEaQdJXQCLJ1hPI%0D%0Af3srR2TNeQUtpi%2FjG7QhP1s2K6L4Xy0bMiE%2FjjvZK56%2FpNiVWeb1HAul1YEBgNOh%0D%0ATl0nZsA9yjcyAjiGeUC42CWgThzyT%2B5F9KmWo%2FOJHbSQt3Gze7L7Sf0ZmIrlZ%2FUi%0D%0AyNs8CavZIBZgix2KdRWelg3KeMUbnaF7L9Ste4VtMNyYj2irSoYMJVuHLI3nOgcA%0D%0Ai86NjQtO%2BUesInZz%2FW5yICWWi6va81UAaykV%2FaxUi627KOrRJ7M2IDq7RLy0UNEU%0D%0A%2BzGmZnZ4%2FArQtojonJJqDqxQbcuYMbZfisJnhB4Xu3ezWEsG5lfizgLjfvdh65EN%0D%0A8eTUOXHpHNb5jm2bQgS8rrXqcI8DL5YZeJKHd0TQ42HxHHOOxAqioRyKEdbmnHax%0D%0A%2Fhq8mz37oDPBBTZ4tMGzs7LRm2cTgjQhBauCAFhYsSr9VrvgsdUFMXgba6hR5KIM%0D%0ABvnrDznT4gA0cDeMIRITmUOd9CRN%2F76wiUSkYjlcD%2B2%2B4tAz5fITizEQpYIZhkBt%0D%0Aq047KDirYdfCpswGlU9I8HSkgeOUrjVOX3kIcZQNz38ki7lj%2Fg6yUeN0DfDOZt31%0D%0AqPSHgQch3U6WD10EWBf8TjIC0w2Yd%2BHc3G6FVh0uq6ZE5pBZI4tp1zHek28Tq557%0D%0AzSpDmVO6OwiilLMGTX9GhFVnmTHOZR%2BNmIs9Fa54RF0Tqn%2BVaCSfAfcTXOcIMhT8%0D%0AiiyMYGcDYa6d%2BNTT7xfeiaGwqLeI9anKHRvIQolwoaDlOP1Zqua%2FEpc7K9WvR9F2%0D%0AipEW8dUjAAzqk0vYcRzHR0YlmmlCu1notjQ9KGCct5GMFH8Ng1WkSaBM3gdoJ%2Bm3%0D%0AKRtnN0fL2L3Uf2IYaNp9RYoUO9u2smXcsZ7JjTlQNN%2BN9gAMuPNx9%2Bq%2Bv9bAyATt%0D%0AZLbGQyK%2BQeesUXxX9ifa0Se83LIIE0%2BNm8kZ3KvZzm3EjWIWxe4Vt%2BfFpij0Pqvq%0D%0AEHAGG6Ei%2B8%2FQGOcUe1uU7t8jbnOzjlzB2izqJy%2F9Rwc8uPxl3vtngEy%2BAWicUxon%0D%0AIPwvjjCN96LgnF4lhh1Im1oDtJLz%2F6Skc5mEsktqSr5bpFYQMk8P7kvQuImyGeLI%0D%0A369w0OX8ZgYrkMDie5Q23wvJ7dcXk5ocFHvUhCVbveNoqExOIkJDErqHJA64vMpY%0D%0AxbpqYb9MdnpfA9EcbsMU%2F59hMDCwwmd7NRkhhp%2FmGyWUTJcN%2BbYHSqOJZeHNeXn0%0D%0ApYMDS2amNACrcjGd8tnI%2FrKJptNkYrGhtjLTreXOjqtxRRMIAA0E6K1RY5WYgmjs%0D%0Aqotg2WvzySqU2zM6ozT6b6jYK2FRnGue2zIW3vVbpC%2B8FT7IIm4AC64dxfpSP%2FPx%0D%0AtLrAyAX4X9DrLOw2dj%2BXNYeHs8xSflQP7WrI7fGaj2Yf4d0OyFRy7vRWRJmHR2AO%0D%0AOpEGojwMvRlE0uSGuZBQUl247mHKP%2F7uBNbwJ43bsX6y%2BtQqNIeXXJmm54PT81%2B7%0D%0ACyUtkhb61sejhgHMLigI%2BmaozV7RyJP%2FCeqBCRiAt7TUSi55EWB5ZTMvFU6oQ5RX%0D%0AkFCfsKMJn71RrcjawTnQSJDrrAoZ7%2BwYwSt1araPbNVgrSGOhxcfITKZ9t9UZRFD%0D%0ApFUbWsT9XhOcPgBEtOJUF%2FRoFMn5Sx%2BZKzUWvPk4nfhXrRu5GaBRR1%2FNDZ8HA9u%2F%0D%0AyiEkrHvADo%2BFIXY5L8XPq35Dfiydk%2FL5klSAWdrJP3pGltJ2UYqARnIEhvOfsUcG%0D%0AqPFwfS8DtNYlojGlEhM7y4ksLzF9mjZdEeLzMtTm4NyACHf9UyKIgvQ%2BDF5rf8%2BY%0D%0AI1SrJSklVioyeHZRopZuWol4XmbIiaIJTHq2fmn20JN4Ohw0r%2B1hSAEeUanETC41%0D%0AEGQwiJkDTS9Mk9PZhD5VnpnNJbMhJFS3dSmf8IlknZgsx9HZwaTpJ%2BSeRKhHhOVV%0D%0A5xdSGzFBZGEGjBtynRYlIHc36vt0oVBPpjBqkGl%2FtryBRldTvrsfqIVLU2FlXCHY%0D%0A0wVbVuunKvmTZ7lXJgfU08P1HTJ4FyZPUAOscfV6cRxKVWCn%2Bqzo7NoYRg4DYQKs%0D%0AWwVHnG9j2kfJBSdwhBSQFG4bHYhEv16dv4juJUqU1Mpz3XQEpOUZHQoLWI7wxD0h%0D%0AUu6ZdHaBfzuIF%2BOgoYo3mfAmu3ip8U%2BonzXjcxHrPpml%2FLKWAyA80MOfAvDlCbRr%0D%0AWWfXmazC5fTvMOoPjm5DOb1LyJv%2BNt8IiUr9PQBeJjPYGw0j3%2FIdxmii8%2FaSP862%0D%0ASbs3D2x9cIXHHuy%2FR9rDGEVbmLnyuRgLnindvGe9H%2BWrJ47HrtiXTpTdFrXz5DQx%0D%0AaaGNJ84Ru2VnntuhpfdmagT02HjQGLvVHuTxnN06itlCX18WQWtRA8QphvnxBQFj%0D%0ArwTd7lqGOs994LtGLhAquv%2FVYQuwC79dK3NyJ92Mu2nlrbU64zuPAD7zqU96KyRv%0D%0AGtDKnBV04kFHgv7NHQFo8KAhYUyEtpWTf%2F3YDF8W5hYtBtzFmKW%2Bhca8bD18rCtj%0D%0AolJ8teB1frDFX9e9qtWCXptFX98huiC4%2FY48IFUjr8egiXb%2FRWhq92B3L3H6k59d%0D%0Ad91NbhCUfQnFPdvNI6kbUT27X96dYDrknZA7IWderdRtnFZWEB%2FtxfXar9TDy%2F1H%0D%0A80C1xABjqQQfT3AGggQmWeHOdA3S8r8JFidmFSdr4m38%2F%2BY2SeOwsaLyHCEKbN9K%0D%0AX2ow2u8NL6e5HLKvsPeeBkKQG%2FNXgLzrid%2BRtgfwEg8TA4LFKaUrNaxpMaSNGdMc%0D%0ANYyegmgKJoobUHLiGWKf5d77MlLM5zFVhaBsKKLBlNfltccK7aLRRH3qVIaLGBaL%0D%0ACfm84O5Sl2%2BaGCr1R8L5l0yZPETpjoElsBmqZJlbfjjCLegqqKErnPWwc3Wg5exk%0D%0ApVYvOgnYADUWvGHvt%2FzWtfeGNJbrvmdCB0mo4UUE72JpjjhPwJdNFfA%2ByzRNpV4M%0D%0AzI3tnsDRYXwBPk%2FmFQ7D7oa%2B6mQgif%2F%2B5brJX%2FTXQrgXSpLDWN7FcNqJai0FKFMU%0D%0AtPbebqHPjUJVuhtaqlO6%2F5Kj%2B9CjGOX8X1cG5rZUbpvHOs5ktVo7BLmRikDz9jHo%0D%0APACIJCFr7jmZBvobnr0dILncJ7wN%2B6xh%2BQErRPE5mlKqUqzMxlkgYzsn3e%2FIxDRs%0D%0ALTu2Uzn0NyjAKlTBFiEQ2L%2FMh2XAAxbb2t925bPENbJfs0o07h%2FrQ13XhjagL0Uw%0D%0AE1SbigPdCtXtIqxyx9zxiqELxsmOSMCza9RRCwum6qnKYORhM6C9O%2BqCgk2CRKsl%0D%0AXwjRLyFiWFa5x%2BNU2DlkaJzzTsj3CuuOx0GdiO9AlikBTn4Y%2FwfnMTwQRrGEXOdW%0D%0A87R%2B%2Bbq6QtSAkdprE9gMjJKJdQmMlHpFHGe%2BcfzAULO5tg0QlxeTFbBYunRhDchH%0D%0AZG7F7lW3RcNyBKusjmCZVzyyVWLVuxoY4HseDnUrTP10bKRHY1WOVrptdRZ4OLb1%0D%0APxg%2FQoXk%2BBnJ1IaPhfcOoByHZcjG3rXeMhWvP7npZOzz7%2Fy5w9Rjlj1zbfNSW0S6%0D%0AJ4QzJwAHGy%2BxdqhrlXlC4OhvBDsbwHtXiL0HiGCMFU7MUWcmYSfBZwOb3p7skCRQ%0D%0AXk2ONnk67vKY7FRQWzTpKaFbyOvAyETxMWzLjQJGA%2BFeruy05Gfj8DqLsSM2qfU%2F%0D%0A5GYTekH7M8zFqWmMDWbEql40DPxavDR%2FOfExfcJFuIB7XerHKwlJWKY8MHLC4jJh%0D%0AFztux8Cav8ojnHRZN75NN55ufZA0vYObIHIt9iTbaDdZIB84IsX9lTHyiepQUERa%0D%0AnaY7NSzTCCXNouwoXXvjIBW6zjqVXoqyUsnZQXScnWWsOoD1dNpURorqmzhB%2B8Td%0D%0AJ6OB9KJR5YEdu%2Bdb3Y%2FCct0na98xzGz1G7Ph7eIpx6tJxBhqjJnUzBiAmOL0fdLf&browserType=Chrome&txversion=5.0&osVersion=10&requestUrl=https%3A%2F%2Fdkpg-web.payments.kakao.com%2F&currency=WON&subCompanyTel=&timestamp=1755013432055&ansim_quota=&address=&requestTimestamp=1755013432969&targetTop=true&postNum=&mobileType=false&offerPeriod=&cartResultString=&pgAuthIp=&INIregno=&no_moid2=&closeUrl=https%3A%2F%2Fdkpg-web.payments.kakao.com%2Fdkpg%2Fv1%2Fpayment%2Finicis%2Fcard%2Fcancel_web%3Fsession_key%3D1755013427127-a0882600-0b66-4800-ac90-304500fa9bee" + \
                                          "&cartString=&clientIp=" + clientIp + "&ip_event=&isAbleCheck=&billPrint_msg=&buyername=%EB%A9%9C%EB%A1%A0%ED%8B%B0%EC%BC%93&mKey=246f541a34eeb94f7554f0b38e8eed7c20b0ac639baf9f00d3e8fe5a5b2d38f3&rentalCompNo=&rentalCompNm=" + \
                                          "&ini_cardcodebanner_url=&cupDeposit=&dboption=&selMpi=&memberUniqueId=&browserVersion=&NAVR_SP_CHAIN_CODE=&additionalData=&rentalRecipientPhone=&addressDtl=&goodscnts=&rentalPeriod=&custemail=&tax=&requestByJs=true" + \
                                          "&privateCss=&rentalRecipientNm=&subCompanyBoss=&ini_SSGPAY_MDN=&ini_SSGPAY_PRODUCTCODE=10000000001&languageResult=&smid=&fds_result=&goodsname=2025+KAI+SOLO+CONCERT+TOUR+%E3%80%88KAION%E3%80%89+..." + \
                                          "&oid=8010000459733319&ini_CI=&subCompanyNum=&sid=&limitTime=30&nointerest=&goodsprice=&selectPayMethod=Card&subCompanyName=&ini_cardcode=&osType=Windows&messageVersion=" + \
                                          "&returnUrl=https%3A%2F%2Fdkpg-web.payments.kakao.com%2Fdkpg%2Fv1%2Fpayment%2Finicis%2Fcard%2Fapprove_web&goodscnt=&rentalPrice=&use_chkfake=Y&customized_msg=&p_noti=&uway_comp_nm=&ini_SSGPAY_PRODUCTINFO=" + \
                                          "&goodsnames=&fakeSign=3034dcc9849c7e48beda4d55130ec832f4d53b402d63c4ca6819d3d7b6cb507c&noteUrl=&voucherGokr=&ini_onlycardcode=&encrypted=&escrowData=&merchantData=&inputAllCheck=T&inputChk7Check=" + \
                                          "&inputChk3Check=&inputChk4Check=&scriptDate=1755013456410"
                    requestResponse = client.post(strRequestUrl, strRequestParameter)
                    if (requestResponse.status_code == 200):
                        strResponseHtml = requestResponse.text
                        dicResponseResult = json.loads(strResponseHtml)

                        if "resultCode" in dicResponseResult:
                            resultCode = dicResponseResult["resultCode"]
                            if strCaptchaKey != "":
                                excuteState = 13
                            LogMessage(strResponseHtml)
                elif excuteState == 13:
                    break
                time.sleep(random.uniform(requestInterval, requestInterval + 200) / 1000)
            else:
                time.sleep(1)
        except Exception as e:
            LogMessage("线程执行异常，异常信息为："+ str(e))
            time.sleep(3)



def process_jsonp_response_robust(response_body, callback):
    if not callback:
        return ""
    # 去除响应体两端的空白字符
    response_body = response_body.strip()
    # 检查是否是有效的 JSONP 响应
    jsonp_pattern = re.compile(rf"^{re.escape(callback)}\((.*)\);?$", re.DOTALL)
    match = jsonp_pattern.match(response_body)
    if match:
        # 提取 JSON 内容
        return match.group(1)
    return response_body  # 如果不是 JSONP 格式，直接返回原始内容

u=UiWindow()
def LogMessage(message):
    global_resources.logger.info(message)
    u.change_text_output(message)


event_handler = LogMessage


