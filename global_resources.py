import configparser

from logger import Logger
blStartGrab = False
cookies = {}
headers = {}  # 新增：存储请求头
proxies = []   # 新增：存储代理列表
config = configparser.ConfigParser()
config.optionxform = str
config.read('config.ini', encoding='utf-8')

# 读取Cookie [COOKIES] 节
if 'COOKIES' in config.sections():
    full_cookie = config.get('COOKIES', 'full_cookie', fallback='')
    cookie_keys = [k for k in config['COOKIES'].keys() if k != 'full_cookie']
    cookies = {k: config['COOKIES'][k] for k in cookie_keys}
if 'HEADERS' in config.sections():
    headers = dict(config['HEADERS'])
    
# 读取代理列表 [PROXIES] 节
if 'PROXIES' in config.sections():
    # 提取proxy开头的键并按数字排序
    proxy_keys = sorted(config['PROXIES'].keys(), key=lambda k: int(k.replace('proxy', '')))
    proxies = [config['PROXIES'][key] for key in proxy_keys]
    proxies.clear()
    
referUrl=""
#raw_cookie = config['config']['cookie']
#raw_header = config['config']['header']
#raw_proxies = config['config']['proxys']
TimeDelay = float(config['settings']['timedelay'])
UserName = config['settings']['username']
telNum = config['settings']['telNum']
MemberKey = config['settings']['memberkey']
EventID = config['settings']['eventid']
ScheduleNo = config['settings']['scheduleno']
areaNo = config['settings']['areaNo']

seatType = config['settings']['seattype']
#mapClickYn = config['settings']['mapClickYn']
user_accounts = []  # 用于存储账户名
logger=Logger()

seatId = ""
seatName = ""
encryptedSeatIds=""