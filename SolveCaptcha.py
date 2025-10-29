import base64
import os
from io import BytesIO
from PIL import Image, ImageFilter
import numpy as np
import pytesseract
import cv2

# 安装Tesseract，指定项目里的 tesseract.exe
#pytesseract.pytesseract.tesseract_cmd = os.path.join("C:\\Program Files\\Tesseract-OCR", "tesseract.exe")
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

    # 4️⃣ 自适应阈值二值化
    np_binary = cv2.adaptiveThreshold(np_gray, 255,
                                      cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY, 11, 2)

    # 5️⃣ 轻微去噪
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
    np_clean = cv2.morphologyEx(np_binary, cv2.MORPH_OPEN, kernel)

    # 6️⃣ 去掉大黑边并增加边距
    coords = np.column_stack(np.where(np_clean > 0))
    if coords.size == 0:
        return "识别失败：未找到非黑区域"

    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    margin = 2  # 增加边距
    y0 = max(y0 - margin, 0)
    x0 = max(x0 - margin, 0)
    y1 = min(y1 + margin, np_clean.shape[0] - 1)
    x1 = min(x1 + margin, np_clean.shape[1] - 1)
    cropped = np_clean[y0:y1 + 1, x0:x1 + 1]

    # 7️⃣ 放大图像
    h, w = cropped.shape
    cropped_resized = cv2.resize(cropped, (w * 4, h * 4), interpolation=cv2.INTER_LINEAR)
    pil_img = Image.fromarray(cropped_resized)

    # 8️⃣ OCR识别：逐个字符，拼接保证最后字符识别
    data = pytesseract.image_to_data(
        pil_img,
        config="--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        output_type=pytesseract.Output.DICT
    )
    text = ''.join([c for c in data['text'] if c.strip() != ''])

    return text.strip()
