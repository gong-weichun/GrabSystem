import random
import tls_client
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
import threading
import time

import global_resources

COOKIES_JSON = "cookies_for_playwright.json"

proxies = global_resources.proxies
cookies = global_resources.cookies
headers = global_resources.headers


class TLSHttpClient:

    def __init__(self):

        self.session = tls_client.Session(
            client_identifier="chrome_117",
            random_tls_extension_order=True,
            force_http1=True
        )

        # 记录上一次URL
        self.last_url = None

        if headers:
            self.session.headers.update(headers)

        if cookies:
            for k, v in cookies.items():
                self.session.cookies.set(k, v)

        self.proxies = proxies or []

    def update_referer(self):
        """自动更新Referer"""
        if self.last_url:
            self.session.headers["Referer"] = self.last_url

    def get(self, url):

        while True:
            proxy = self.get_proxy()

            if global_resources.referUrl != "":
                # 更新Referer
                self.session.headers["Referer"]=global_resources.referUrl
                #self.update_referer()

            print(self.session.cookies.get("JSESSIONID", domain="tkglobal.melon.com"))
            response = self.session.get(url)  # ,proxy=proxy

            # 更新last_url
            #self.last_url = url

            if response.status_code == 200:
                return response
            elif not self.proxies:
                return response
            else:
                self.proxies.pop(0)

    def post(self, url, data=None, json=None):

        while True:
            proxy = self.get_proxy()

            if global_resources.referUrl != "":
                # 更新Referer
                self.session.headers["Referer"] = global_resources.referUrl

            print(self.session.cookies.get("JSESSIONID", domain="tkglobal.melon.com"))
            response = self.session.post(url, data=data)  # ,json=json,proxy=proxy

            # 更新last_url
            #self.last_url = url

            if response.status_code == 200:
                return response
            elif not self.proxies:
                return response
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
    def playwright_login_and_get_cookies(self,login_url):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, channel="chrome")
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

