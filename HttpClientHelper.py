import random
import tls_client
from playwright.sync_api import sync_playwright
import threading
import time

# 配置代理池
# -------------------------------
proxies = [
    "http://928:928@211.54.252.92:25510",
    "http://928:928@169.214.171.225:25510",
    "http://928:928@183.109.129.241:25510",
    "http://928:928@220.90.167.177:25510",
    "http://928:928@222.105.21.103:25510",
    "http://928:928@210.126.113.136:25510",
    "http://928:928@118.43.185.220:25510",
    "http://928:928@175.202.27.148:25510",
    "http://928:928@118.43.185.133:25510",
    "http://928:928@210.126.113.248:25510",
    "http://928:928@211.230.230.62:25510",
    "http://928:928@222.105.68.189:25510",
    "http://928:928@222.105.68.177:25510",
    "http://928:928@59.2.199.151:25510",
    "http://928:928@118.43.185.22:25510",
    "http://928:928@211.230.223.250:25510",
]
cookies={
        "_fwb": "166xWFGnpSm3zmDAWMSqxxm.1751968344908",
        "PCID": "17535241246108694755228",
        "TKT_POC_ID": "WP19",
        "i18next": "EN",
        "JSESSIONID": "5FCEDB523E90C194801D89BCA21083B4",
        "NetFunnel_ID": "WP15",
        "keyCookie_T": "1007828360",
        "MAC_T": "\"fH2/f7duFWy4ZLwt+GBVbxDywEUCDOfjmzh3qU0mZw3fhWhXKiBixr8Nv9fvXkkkTzGCTuSSmdM3tqab4nfCPA==\"",
        "wcs_bt": "s_322bdbd6fd48:1758192186"
}
headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/116.0.5845.110 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
                      "application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        }
class TLSHttpClient:
    def __init__(self):#cookies=None, headers=None, proxies=None

        # 1. 创建客户端，模拟 Chrome 浏览器
        self.session  = tls_client.Session(
            client_identifier="chrome_117",
            random_tls_extension_order=True,
        )  # 也可以选择 firefox_115, edge_116 等
        # 设置全局 Headers
        if headers:
            self.session.headers.update(headers)

        # 初始化 Cookies
        if cookies:
            for k, v in cookies.items():
                self.session.cookies.set(k, v)
        # 代理池
        self.proxies = proxies or []

    def get(self, url):
        # 发起 GET 请求
        while True:
            proxy = self.get_proxy()
            response = self.session.get(url,proxy=proxy)
            if response.status_code == 200:
                return response
            elif not self.proxies:
                return None
            else:
                self.proxies.pop(0)
    def post(self, url, data=None, json=None):
        # 发起 POST 请求
        while True:
            proxy = self.get_proxy()
            response = self.session.post(url,data=data, json=json,proxy=proxy)
            if response.status_code == 200:
                return response
            elif not self.proxies:
                return None
            else:
                self.proxies.pop(0)

    def get_proxy(self):
        """取第一个代理"""
        if not self.proxies:
            return None
        return self.proxies[0]
    def playwright_request(self,url):
        # 获取 Cookies 用于 Playwright
        cookies = self.session.cookies  # dict 格式

        # 转换为 Playwright 可以使用的列表格式
        playwright_cookies = []
        for name, value in cookies.items():
            playwright_cookies.append({
                "name": name,
                "value": value,
                # "domain": ".example.com",  # 修改为目标域
                # "path": "/",
                # "httpOnly": False,
                # "secure": True,
            })

        # =====================
        # Playwright 请求
        # =====================
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()

            # 设置 cookies
            context.add_cookies(playwright_cookies)

            page = context.new_page()
            page.goto(url)
            #print("Playwright 页面标题:", page.title())

            # 获取页面内容
            content = page.content()
            #print("页面前200字符:", content[:200])
