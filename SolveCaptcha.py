import base64
import os
from io import BytesIO
from PIL import Image, ImageFilter
import numpy as np
import pytesseract
import cv2

# 安装Tesseract，指定项目里的 tesseract.exe
pytesseract.pytesseract.tesseract_cmd = os.path.join("C:\\Program Files\\Tesseract-OCR", "tesseract.exe")

def ocr_image_from_base64_advanced(base64_data):
    # 1️⃣ 解码 Base64 并打开图片
    image_bytes = base64.b64decode(base64_data)
    image = Image.open(BytesIO(image_bytes)).convert("RGB")  # 确保标准 Image 对象

    # 2️⃣ 转灰度
    gray = image.convert("L").copy()
    np_gray = np.array(gray, dtype=np.uint8)

    # 3️⃣ OpenCV 二值化
    _, np_binary = cv2.threshold(np_gray, 100, 255, cv2.THRESH_BINARY)

    # 4️⃣ 形态学操作：去掉干扰线和小噪点
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
    np_clean = cv2.morphologyEx(np_binary, cv2.MORPH_OPEN, kernel)  # 开运算去小噪点
    np_clean = cv2.medianBlur(np_clean, 3)  # 中值滤波平滑残余噪点

    # 5️⃣ 去掉大黑边
    coords = np.column_stack(np.where(np_clean > 0))
    if coords.size == 0:
        return "识别失败：未找到非黑区域"
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    cropped = np_clean[y0:y1+1, x0:x1+1]

    # 6️⃣ 放大图像，提高识别率
    h, w = cropped.shape
    cropped_resized = cv2.resize(cropped, (w*2, h*2), interpolation=cv2.INTER_LINEAR)

    # 7️⃣ 转回 PIL Image 做 OCR
    pil_img = Image.fromarray(cropped_resized)

    # 8️⃣ OCR识别
    config = "--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    text = pytesseract.image_to_string(pil_img, config=config)

    return text.strip()
