import datetime
import time
import tkinter as tk
from tkinter import scrolledtext
import threading

import global_resources


class UiWindow:
    _instance = None  # 用来保存当前UI实例
    def start_ui_task(self):
        threading.Thread(target=self.set_ui).start()

    def __init__(self):
        UiWindow._instance = self

    def set_ui(self):

        root = tk.Tk()
        root.title("主界面")
        root.geometry("1000x800")
        root.configure(bg="#f5f5f5")

        # ===== 顶部：用户名和密码 =====
        frame_top = tk.Frame(root, bg="#f5f5f5")
        frame_top.pack(pady=10, fill="x")

        tk.Label(frame_top, text="用户名:", bg="#f5f5f5").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.entry_username = tk.Entry(frame_top, width=40, textvariable=tk.StringVar(value="877605465@qq.com"))
        self.entry_username.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(frame_top, text="EventID:", bg="#f5f5f5").grid(row=0, column=2, sticky="w", padx=10, pady=5)
        self.entry_eventid = tk.Entry(frame_top, width=20, textvariable=tk.StringVar(value=global_resources.EventID))
        self.entry_eventid.grid(row=0, column=3, padx=10, pady=5)

        tk.Label(frame_top, text="密码:", bg="#f5f5f5").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.entry_password = tk.Entry(frame_top, show="*", width=40, textvariable=tk.StringVar(value="gg4718910"))
        self.entry_password.grid(row=1, column=1, padx=10, pady=5)

        tk.Label(frame_top, text="ScheduleNo:", bg="#f5f5f5").grid(row=1, column=2, sticky="w", padx=10, pady=5)
        self.entry_scheduleno = tk.Entry(frame_top, width=20, textvariable=tk.StringVar(value=global_resources.ScheduleNo))
        self.entry_scheduleno.grid(row=1, column=3, padx=10, pady=5)

        # ===== 中部：按钮区 =====
        frame_buttons = tk.Frame(root, bg="#f5f5f5")
        frame_buttons.pack(pady=10)

        tk.Button(frame_buttons, text="添加用户", width=12, command=self.add_account).pack(side="left", padx=5)
        tk.Button(frame_buttons, text="清空日志", width=12, command=self.clear_output).pack(side="left", padx=5)

        # ===== 滑块区 =====
        frame_slider = tk.Frame(root, bg="#f5f5f5")
        frame_slider.pack(pady=10)

        tk.Label(frame_slider, text="延迟时间 (ms):", bg="#f5f5f5").pack(side="left", padx=5)
        self.slider_value = tk.DoubleVar(value=400)

        # 在滑块释放后自动触发更新
        slider = tk.Scale(
            frame_slider,
            from_=0,
            to=1000,
            orient="horizontal",
            variable=self.slider_value,
            length=300,
            bg="#f5f5f5",
            # command=self.on_slider_move
        )
        slider.pack(side="left", padx=10)

        # ===== 开始 / 结束按钮 =====
        frame_actions = tk.Frame(root, bg="#f5f5f5")
        frame_actions.pack(pady=10)

        btn_start = tk.Button(frame_actions, text="开始", width=12, bg="green", fg="white",
                              command=self.change_blStartGrab)
        btn_start.pack(side="left", padx=10)

        btn_stop = tk.Button(frame_actions, text="结束", width=12, bg="red", fg="white",
                             command=self.change_blStartGrab)
        btn_stop.pack(side="left", padx=10)

        # ===== 输出区（日志） =====
        frame_output = tk.Frame(root, bg="#f5f5f5")
        frame_output.pack(padx=10, pady=5, fill="both", expand=True)

        tk.Label(frame_output, text="日志输出:", bg="#f5f5f5").pack(anchor="w")
        self.text_output = scrolledtext.ScrolledText(frame_output, width=70, height=8, font=("Consolas", 10))
        self.text_output.pack(fill="both", expand=True)

        # ===== 输出区（账户列表） =====
        frame_accounts = tk.Frame(root, bg="#f5f5f5")
        frame_accounts.pack(padx=10, pady=5, fill="both", expand=True)

        tk.Label(frame_accounts, text="账户列表:", bg="#f5f5f5").pack(anchor="w")
        self.text_accounts = scrolledtext.ScrolledText(frame_accounts, width=70, height=6, font=("Consolas", 10))
        self.text_accounts.pack(fill="both", expand=True)

        # 绑定释放事件（鼠标放开滑块时触发）
        slider.bind("<ButtonRelease-1>", self.on_slider_release)

        root.mainloop()

    def add_account(self):
        username = self.entry_username.get().strip()
        if username:
            global_resources.user_accounts.append(username)
            self.text_output.insert(tk.END, f"[添加账户] {username}\n")
            self.refresh_account_list()
        else:
            self.text_output.insert(tk.END, "[警告] 用户名不能为空！\n")

    def refresh_account_list(self):
        self.text_accounts.delete(1.0, tk.END)
        for idx, acc in enumerate(global_resources.user_accounts, start=1):
            self.text_accounts.insert(tk.END, f"{idx}. {acc}\n")

    def clear_output(self):
        self.text_output.delete(1.0, tk.END)

    # def on_slider_move(self, val):
    #     """拖动时显示当前值但不更新全局变量"""
    #     self.change_text_output(f"当前延迟值: {float(val):.0f} (未释放)")

    def on_slider_release(self, event):
        """释放滑块后自动赋值"""
        global_resources.TimeDelay = self.slider_value.get()
        self.change_text_output(f"已更新 TimeDelay = {global_resources.TimeDelay:.0f}")

    def change_text_output(self, value):
        def _update():
            if self.text_output:
                self.text_output.insert(
                    tk.END,
                    f"{datetime.datetime.now().strftime('%H:%M:%S')}：{value}\n"
                )
                self.text_output.see(tk.END)
        self.text_output.after(0, _update)

    def change_blStartGrab(self):
        global_resources.EventID = self.entry_eventid.get()
        global_resources.ScheduleNo = self.entry_scheduleno.get()
        global_resources.blStartGrab = not global_resources.blStartGrab
        self.change_text_output(f"blStartGrab 状态切换为: {global_resources.blStartGrab}")
