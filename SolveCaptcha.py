import os
import pytesseract
import re
import time
import base64
import random
import requests
from io import BytesIO
from typing import Callable, Optional

import tls_client
from PIL import Image
import numpy as np
import cv2
# 获取当前项目路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 安装Tesseract，指定项目里的 tesseract.exe
pytesseract.pytesseract.tesseract_cmd = os.path.join("C:\\Program Files\\Tesseract-OCR", "tesseract.exe")

# ---------- image utilities ----------
def base64_to_pil(b64str: str) -> Image.Image:
    """支持 data URI 或裸 base64"""
    if b64str.startswith("data:"):
        b64str = b64str.split(",", 1)[1]
    imgdata = base64.b64decode(b64str)
    return Image.open(BytesIO(imgdata)).convert("RGB")

def preprocess_for_ocr(pil_img: Image.Image,
                       scale: int = 2,
                       blur_k: int = 3,
                       threshold_method: str = "otsu",
                       morph_kernel: int = 2) -> Image.Image:
    """
    对 PIL 图片进行放大、灰度、去噪、二值化和形态学处理，返回 PIL.Image（单通道或RGB）
    """
    # PIL -> OpenCV
    img = np.array(pil_img)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    # 放大
    if scale != 1:
        img = cv2.resize(img, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # 灰度
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 去噪（中值滤波）
    if blur_k and blur_k > 1:
        gray = cv2.medianBlur(gray, blur_k)

    # 二值化
    if threshold_method == "otsu":
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif threshold_method == "adaptive":
        th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 11, 2)
    else:
        _, th = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

    # 形态学操作去噪（开、闭）
    k = np.ones((morph_kernel, morph_kernel), np.uint8)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, k)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, k)

    # 返回 PIL 图像（单通道）
    return Image.fromarray(th)

def ocr_from_pil(pil_img: Image.Image, whitelist: Optional[str] = None, psm: int = 7) -> str:
    """调用 pytesseract 识别 PIL 图像，返回清理后的文本"""
    config = f'--psm {psm}'
    if whitelist:
        # 限定字符集能显著提高准确度
        config += f' -c tessedit_char_whitelist={whitelist}'
        try:
            text = pytesseract.image_to_string(pil_img, config=config)
        except Exception as e:
            print("base64_to_pil error:", e)
            return ""
    return text.strip()

def ocr_from_base64(b64str: str,
                    whitelist: Optional[str] = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
                    try_scale=True) -> str:
    """
    尝试若干预处理步骤识别 base64 验证码（本地 OCR）
    返回识别文本（失败返回空字符串）
    """
    try:
        pil = base64_to_pil(b64str)
    except Exception as e:
        print("base64_to_pil error:", e)
        return ""

    # 直接识别原图（快速路径）
    txt = ocr_from_pil(pil, whitelist=whitelist, psm=7)
    if txt and len(txt) > 0:
        return txt

    # 预处理路径
    for scale in (2, 3):
        proc = preprocess_for_ocr(pil, scale=scale, blur_k=3, threshold_method='otsu', morph_kernel=2)
        txt = ocr_from_pil(proc, whitelist=whitelist, psm=7)
        if txt and len(txt) > 0:
            return txt

    # 最后尝试更激进的阈值/自适应
    proc = preprocess_for_ocr(pil, scale=2, blur_k=1, threshold_method='adaptive', morph_kernel=1)
    txt = ocr_from_pil(proc, whitelist=whitelist, psm=7)
    return txt or ""

