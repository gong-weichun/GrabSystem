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


        if headers:
            self.session.headers.update(headers)

        if cookies:
            for k, v in cookies.items():
                domain = "tkglobal.melon.com"
                if k in ["PCID", "keyCookie_T", "MAC_T", "NetFunnel_ID", "TKT_POC_ID"]:
                    domain = ".melon.com"
                self.session.cookies.set(k, v,domain=domain,path="/",secure=True)

        self.proxies = proxies or []


    def get(self, url):

        while True:
            proxy = self.get_proxy()

            if global_resources.referUrl != "":
                # 更新Referer
                self.session.headers["Referer"]=global_resources.referUrl
            global_resources.referUrl=""

            print(self.session.cookies.get("JSESSIONID", domain="tkglobal.melon.com")+"——"+url)
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
            global_resources.referUrl = ""

            print(self.session.cookies.get("JSESSIONID", domain="tkglobal.melon.com") + "——" + url)

            # ❗关键：禁止自动跳转
            response = self.session.post(url, data=data, allow_redirects=False)

            # ✅ 处理 302
            if response.status_code in (301, 302):
                location = response.headers.get("Location")
                print("302 ->", location)

                if location:
                    # 绝对路径处理
                    if location.startswith("/"):
                        location = "https://tkglobal.melon.com" + location

                    # 更新 Referer（非常关键）
                    self.session.headers["Referer"] = url

                    # 手动 GET 跳转
                    response = self.session.get(location, allow_redirects=False)

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
    def playwright_request(self, url):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, channel="chrome")

            context = browser.new_context(
                user_agent=self.session.headers.get("User-Agent", "")
            )

            # ✅ 正确提取 cookie（完整属性）
            playwright_cookies = []
            for domain, paths in self.session.cookies._cookies.items():
                for path, cookies in paths.items():
                    for name, c in cookies.items():
                        playwright_cookies.append({
                            "name": c.name,
                            "value": c.value,
                            "domain": c.domain,
                            "path": c.path,
                            "secure": c.secure,
                            "httpOnly": False,
                        })

            # ✅ 注入 cookie
            context.add_cookies(playwright_cookies)

            page = context.new_page()

            # ⭐ 关键：先打主域，避免 session 重建
            page.goto("https://tkglobal.melon.com", wait_until="domcontentloaded")

            page.goto(url, timeout=60000, wait_until="domcontentloaded")

            print("[playwright] JSESSIONID:",
                  [c for c in context.cookies() if c["name"] == "JSESSIONID"])

            print("[playwright] Page title:", page.title())

            return page

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

