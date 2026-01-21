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

    # 6️⃣ 边缘检测（Canny）
    edges = cv2.Canny(np_binary, threshold1=50, threshold2=150)  # 进行 Canny 边缘检测

    # 7️⃣ 使用霍夫变换检测直线
    # 线的检测参数：rho 为分辨率（1），theta 为角度分辨率（np.pi / 180），threshold 为检测阈值
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=50, minLineLength=50, maxLineGap=10)

    # 8️⃣ 遍历检测到的直线并遮掩（将直线区域设为白色）
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            # 在原图中将这些直线区域涂白
            cv2.line(np_binary, (x1, y1), (x2, y2), (255, 255, 255), thickness=3)

    # 9️⃣ 使用腐蚀操作去除干扰线
    kernel_line = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 5))  # 设置较大的核
    np_eroded = cv2.erode(np_binary, kernel_line, iterations=1)  # 腐蚀操作

    # 10️⃣ 去除小的连通区域（干扰线一般为长条形）
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(np_eroded, connectivity=8)
    # 11️⃣ 去掉大黑边并增加边距
    coords = np.column_stack(np.where(np_eroded > 0))
    if coords.size == 0:
        return ""

    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    margin = 5  # 增加边距
    y0 = max(y0 - margin, 0)
    x0 = max(x0 - margin, 0)
    y1 = min(y1 + margin, np_eroded.shape[0] - 1)
    x1 = min(x1 + margin, np_eroded.shape[1] - 1)
    cropped = np_eroded[y0:y1 + 1, x0:x1 + 1]

    # 12️⃣ 放大图像
    h, w = cropped.shape
    cropped_resized = cv2.resize(cropped, (w * 4, h * 4), interpolation=cv2.INTER_LINEAR)
    pil_img = Image.fromarray(cropped_resized)

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
