import random
import tls_client
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
import threading
import time

import global_resources

COOKIES_JSON = "cookies_for_playwright.json"
# 配置代理池
# -------------------------------
<<<<<<< HEAD
proxies = global_resources.proxies
cookies=global_resources.cookies
headers = global_resources.headers
=======
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
        "PCID": "17519683452676828779915",
        "TKT_POC_ID": "WP19",
        "i18next": "EN",
        "JSESSIONID": "B00128A600FDB2A5B496AC0D0379105F",
        "NetFunnel_ID": "WP15",
        "keyCookie_T": "1007828360",
        "MAC_T": "\"fH2/f7duFWy4ZLwt+GBVb4+JDVUP7+bO+Jk3T2C9OeSF/qUYDD4hODl07igwSSghqGBu1+z3EUU5y68aSjPmtQ==\"",
        "wcs_bt": "s_322bdbd6fd48:1761009008"
}
headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "Accept": "text/javascript, application/javascript, application/ecmascript, application/x-ecmascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        }

>>>>>>> 5de70d07a19437eba6a94c20c9222c95341f0dd1
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
            response = self.session.get(url)#,proxy=proxy
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

    # ---------------------------
    # 2️⃣ Playwright 使用 tls_client cookies
    # ---------------------------
    def playwright_request(self,url):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # headless=True 可不显示浏览器
            context = browser.new_context()

            # 自动迁移 tls_client cookies
            cookies = []
            parsed_url = urlparse(url)
            domain = parsed_url.hostname
            for name, value in self.session.cookies.items():
                cookies.append({
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                })
            # 在 context 创建时设置 user_agent
            context = browser.new_context(
                user_agent=self.session.headers.get("User-Agent", ""),
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
            )
            context.add_cookies(cookies)

            # 新建页面
            page = context.new_page()
            page.goto(url,timeout=60000,wait_until="networkidle")
            print("[playwright] Page title:", page.title())

            # 获取页面内容
            content = page.content()
            print(content[:500])

            # 可以执行 JS
            # result = page.evaluate("() => document.querySelector('h1').innerText")
            # print(result)

            #browser.close()

        # ---------------------------
        # 1️⃣ 用 Playwright 登录并获取 Cookie
        # ---------------------------
        def playwright_login_and_get_cookies(login_url: str):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                page.goto(login_url)

                # 🔽 （根据你的页面结构修改这里的操作）
                page.fill("input[name='username']", "你的用户名")
                page.fill("input[name='password']", "你的密码")
                page.click("button[type='submit']")

                page.wait_for_load_state("networkidle")  # 等待页面加载完毕

                # 获取登录后的 cookies
                cookies = context.cookies()
                browser.close()
                return cookies

