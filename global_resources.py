import configparser

from Logger import Logger
blStartGrab = False
cookies={}
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')
raw_cookie = config['cookie']['cookie']
for part in raw_cookie.split(';'):
    key, value = part.split('=', 1)
    cookies[key.strip()] = value.strip()
headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "Referer":"https://tkglobal.melon.com/reservation/popup/onestop.htm",
            "Accept": "text/javascript, application/javascript, application/ecmascript, application/x-ecmascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8"
        }
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
TimeDelay=500
MemberKey = "1007828360"
EventID = "212207"
ScheduleNo = "100001"
blockId="510,504"
seatId=""
user_accounts = []  # 用于存储账户名
logger=Logger()