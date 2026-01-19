import easyocr
import base64
from io import BytesIO
from PIL import Image
import numpy as np


# 解码Base64数据并转换为图片
def decode_base64_image(base64_data):
    base64_data = base64_data.split(",")[1] if base64_data.startswith("data:image") else base64_data
    image_data = base64.b64decode(base64_data)
    image = Image.open(BytesIO(image_data))
    return image


# 使用EasyOCR进行验证码识别
def ocr_image_from_base64(base64_data):
    # 解码图片
    image = decode_base64_image(base64_data)

    # 使用EasyOCR识别
    reader = easyocr.Reader(['en'])
    result = reader.readtext(np.array(image))

    # 提取识别出的文本（假设验证码为6个字符）
    text = ''.join([res[1] for res in result]).strip()
    return text[:6]  # 确保字符数为6
