import base64
import os
from io import BytesIO
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
import pytesseract
import cv2

# 指定 tesseract.exe 的路径
pytesseract.pytesseract.tesseract_cmd = os.path.join("D:\\Tesseract-OCR", "tesseract.exe")


def ocr_image_from_base64(base64_data):
    # 1️⃣ 去掉 Base64 前缀
    if base64_data.startswith("data:image"):
        base64_data = base64_data.split(",")[1]

    # 2️⃣ 解码并打开图片
    image_bytes = base64.b64decode(base64_data)
    image = Image.open(BytesIO(image_bytes))

    # 处理 RGBA 图片，白色背景
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background

    # 3️⃣ 转灰度
    gray = image.convert("L").copy()
    np_gray = np.array(gray, dtype=np.uint8)

    # 4️⃣ 提高对比度和锐化
    enhancer = ImageEnhance.Contrast(gray)
    gray = enhancer.enhance(2)  # 对比度增强
    gray = gray.filter(ImageFilter.SHARPEN)  # 锐化

    np_gray = np.array(gray, dtype=np.uint8)

    # 5️⃣ 自适应阈值二值化
    np_binary = cv2.adaptiveThreshold(np_gray, 255,
                                      cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY, 11, 2)

    np_binary = remove_single_overlay_curve_full_angle_with_repair(np_binary)
    pil_img = Image.fromarray(np_binary)
    # pil_img.show()

    # 13️⃣ OCR识别：调整 Tesseract 参数和 OCR 引擎
    config = "--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ"  # 仅支持大写字母
    data = pytesseract.image_to_data(
        pil_img,
        config=config,
        output_type=pytesseract.Output.DICT
    )

    # 14️⃣ 处理 OCR 输出：逐个字符，拼接保证最后字符识别
    text = ''.join([c for c in data['text'] if c.strip() != ''])

    # 15️⃣ 如果识别的字符不为 6 个，进行后处理确保字符数为 6 个
    text = text[:6]  # 确保只有 6 个字符

    # 16️⃣ 后处理修正：根据置信度进行修正
    corrected_text = []
    for i in range(len(data['text'])):
        char = data['text'][i]
        conf = int(data['conf'][i])

        # 如果识别置信度较低且字符为"O"，则认为它可能是"Q"
        if conf < 50 and char == "O":
            # 基于上下文判断是否是"Q"
            if i > 0 and data['text'][i - 1] == "Q":  # 如果前一个字符是Q
                corrected_text.append("Q")
            else:
                corrected_text.append("O")
        else:
            corrected_text.append(char)

    # 拼接最终结果
    corrected_text = ''.join(corrected_text).strip()

    # 17️⃣ 确保返回的字符数为6个并且是大写字母
    corrected_text = corrected_text[:6].upper()

    return corrected_text

def remove_single_overlay_curve_full_angle_with_repair(binary):
    """
    binary: 0=黑字，255=白底
    """
    h, w = binary.shape

    # ① 反色
    inv = cv2.bitwise_not(binary)

    # ② 参数
    kernel_len = max(15, w // 4)   # 曲线越长，这个越大
    angles = list(range(-80, 81, 5))  # 多角度扫描（-80° ~ 80°）

    extracted_all = np.zeros_like(inv)

    for angle in angles:
        # ③ 生成水平线核
        base = np.zeros((kernel_len, kernel_len), np.uint8)
        base[kernel_len//2, :] = 1

        # ④ 旋转核
        M = cv2.getRotationMatrix2D(
            (kernel_len//2, kernel_len//2),
            angle,
            1.0
        )
        rotated_kernel = cv2.warpAffine(base, M, (kernel_len, kernel_len))
        rotated_kernel = (rotated_kernel > 0).astype(np.uint8)

        # ⑤ 抽取该方向线段
        lines = cv2.morphologyEx(
            inv,
            cv2.MORPH_OPEN,
            rotated_kernel,
            iterations=1
        )

        extracted_all = cv2.bitwise_or(extracted_all, lines)

    # ⑥ 从原图中减去所有方向线
    removed = cv2.subtract(inv, extracted_all)

    # ⑦ 反色恢复
    result = cv2.bitwise_not(removed)

    # ⑧ 修复字符断裂（闭运算）- 填补字符之间的空隙
    fix_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, fix_kernel, iterations=1)  # 使用较少的闭运算次数

    # ⑨ 进一步膨胀字符区域，修复字符连接处的断裂
    dilation_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))  # 使用更小的膨胀核
    result = cv2.morphologyEx(result, cv2.MORPH_DILATE, dilation_kernel, iterations=1)

    # ⑩ 连通组件分析：确保字符区域是连贯的
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(result)

    # ⑪ 如果检测到的字符区域被过度修改，进行进一步修复
    for i in range(1, num_labels):  # 跳过背景
        # 如果字符的面积过小，可以考虑填补
        if stats[i, cv2.CC_STAT_AREA] < 100:
            # 使用填充的方式进行修复
            mask = (labels == i).astype(np.uint8) * 255
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                cv2.drawContours(result, contours, -1, 255, thickness=cv2.FILLED)

    return result

def remove_single_overlay_curve_full_angle_with_repair1(binary):
    """
    binary: 0=黑字，255=白底
    """
    h, w = binary.shape

    # ① 反色
    inv = cv2.bitwise_not(binary)

    # ② 参数
    kernel_len = max(15, w // 4)   # 曲线越长，这个越大
    angles = list(range(-80, 81, 5))  # 多角度扫描（-80° ~ 80°）

    extracted_all = np.zeros_like(inv)

    for angle in angles:
        # ③ 生成水平线核
        base = np.zeros((kernel_len, kernel_len), np.uint8)
        base[kernel_len//2, :] = 1

        # ④ 旋转核
        M = cv2.getRotationMatrix2D(
            (kernel_len//2, kernel_len//2),
            angle,
            1.0
        )
        rotated_kernel = cv2.warpAffine(base, M, (kernel_len, kernel_len))
        rotated_kernel = (rotated_kernel > 0).astype(np.uint8)

        # ⑤ 抽取该方向线段
        lines = cv2.morphologyEx(
            inv,
            cv2.MORPH_OPEN,
            rotated_kernel,
            iterations=1
        )

        extracted_all = cv2.bitwise_or(extracted_all, lines)

    # ⑥ 从原图中减去所有方向线
    removed = cv2.subtract(inv, extracted_all)

    # ⑦ 反色恢复
    result = cv2.bitwise_not(removed)

    # ⑧ 修复字符断裂（闭运算）- 填补字符之间的空隙
    fix_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, fix_kernel, iterations=2)

    # ⑨ 进一步膨胀字符区域，修复字符连接处的断裂
    dilation_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    result = cv2.morphologyEx(result, cv2.MORPH_DILATE, dilation_kernel, iterations=1)

    # ⑩ 连通组件分析：确保字符区域是连贯的
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(result)

    # ⑪ 如果检测到的字符区域被过度修改，进行进一步修复
    for i in range(1, num_labels):  # 跳过背景
        # 如果字符的面积过小，可以考虑填补
        if stats[i, cv2.CC_STAT_AREA] < 100:
            # 使用填充的方式进行修复
            cv2.drawContours(result, [labels == i], -1, (255), thickness=cv2.FILLED)

    return result


# def remove_single_overlay_curve_full_angle(binary):
#     """
#     binary: 0=黑字，255=白底
#     """
#     h, w = binary.shape

#     # ① 反色
#     inv = cv2.bitwise_not(binary)

#     # ② 参数
#     kernel_len = max(15, w // 4)   # 曲线越长，这个越大
#     angles = list(range(-80, 81, 5))  # 多角度扫描（-80° ~ 80°）

#     extracted_all = np.zeros_like(inv)

#     for angle in angles:
#         # ③ 生成水平线核
#         base = np.zeros((kernel_len, kernel_len), np.uint8)
#         base[kernel_len//2, :] = 1

#         # ④ 旋转核
#         M = cv2.getRotationMatrix2D(
#             (kernel_len//2, kernel_len//2),
#             angle,
#             1.0
#         )
#         rotated_kernel = cv2.warpAffine(base, M, (kernel_len, kernel_len))
#         rotated_kernel = (rotated_kernel > 0).astype(np.uint8)

#         # ⑤ 抽取该方向线段
#         lines = cv2.morphologyEx(
#             inv,
#             cv2.MORPH_OPEN,
#             rotated_kernel,
#             iterations=1
#         )

#         extracted_all = cv2.bitwise_or(extracted_all, lines)

#     # ⑥ 从原图中减去所有方向线
#     removed = cv2.subtract(inv, extracted_all)

#     # ⑦ 反色
#     result = cv2.bitwise_not(removed)

#     # ⑧ 修复字符断裂
#     fix_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
#     result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, fix_kernel, iterations=1)

#     return result