import os
import datetime
# 日志等级
class LogLevel:
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Logger:
    def __init__(self, text_widget=None, log_file="log.txt"):
        """
        log_file: 默认日志文件路径
        """
        self.log_file = log_file

        # 如果日志文件不存在，创建并写入开头
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write(f"=== 程序日志开始: {datetime.datetime.now()} ===\n")

    def log(self, msg, level=LogLevel.INFO):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] [{level}] {msg}"

        # 追加到文件
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(full_msg + "\n")

    def info(self, msg):
        self.log(msg, LogLevel.INFO)

    def warning(self, msg):
        self.log(msg, LogLevel.WARNING)

    def error(self, msg):
        self.log(msg, LogLevel.ERROR)