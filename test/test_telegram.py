import shutil
import socket
import requests
import re

telegram_bot_token = '7855424657:AAEcV7XfkkRUTkoRLUcri2-2S1UzsGfeDxY'
telegram_chat_ids = ['-4606781747']

#telegram_bot_token = '5909048552:AAHvhyE5zFpnNGb4hdp-jQE_mKYBnnYa4go'
#telegram_chat_ids = ['-939998600']
message = '测试'

url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
for chat_id in telegram_chat_ids:
    data = {
        "chat_id": chat_id,
        "text": message
    }
    #response = requests.post(url, data=data)
    #response.raise_for_status()

phone = '13800138000'
phone_hide = phone[:3] + '***' + phone[6:]
print(phone_hide)

from datetime import datetime

# 获取当前时间戳
current_timestamp = datetime.now().timestamp()  # 或 time.time()

# 转为本地时间字符串
current_time_str = datetime.fromtimestamp(current_timestamp).strftime("%Y-%m-%d %H:%M:%S")
print(current_time_str) 



def get_my_ip():
    """获取本机公网IP地址"""
    ip_apis = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
        "https://ident.me",
        "https://ip.anysrc.net/plain",
        "https://myexternalip.com/raw"
    ]
    for api_url in ip_apis:
        try:
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                ip = response.text.strip()
                if ip and re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                    return ip
        except Exception as e:
            continue

    # 如果所有方法都失败，尝试使用系统命令
    try:
        # 尝试使用 curl 命令
        ip = subprocess.check_output(['curl', '-s', 'https://api.ipify.org']).decode('utf-8').strip()
        if ip and re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
            print(f"使用curl命令获取IP成功: {ip}")
            return ip
    except Exception as e:
        print(f"使用curl命令获取IP失败: {e}")

    # 如果所有方法都失败，返回本地回环地址
    print("所有获取IP的方法都失败，使用本地回环地址")
    return "127.0.0.1"


print(get_my_ip())
