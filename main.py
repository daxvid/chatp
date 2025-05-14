import os
import logging
import time
import csv
import ssl
import whisper
import edge_tts
import traceback
import signal
import sys
import pjsua2 as pj
from threading import Event
from datetime import datetime
import subprocess
import shutil
import socket
import requests
import re

from config_manager import ConfigManager
from response_manager import ResponseManager
from tts_manager import TTSManager
from whisper_manager import WhisperManager
from sip_caller import SIPCaller
from call_manager import CallManager

# 禁用全局SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

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
            return ip
    except Exception as e:
        print(f"使用curl命令获取IP失败: {e}")

    # 如果所有方法都失败，返回本地回环地址
    print("所有获取IP的方法都失败，使用本地回环地址")
    return "127.0.0.1"

# 配置日志
def setup_logging(log_file):
    """设置日志配置"""
    # 确保日志目录存在
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


logger = logging.getLogger("main")

# 全局变量
exit_event = Event()
sip_caller = None
services = None
config = None

# 信号处理函数
def signal_handler(sig, frame):
    global exit_event, sip_caller
    logger.info("接收到中断信号，准备安全退出...")
    exit_event.set()
    # 不立即退出，让程序正常完成清理
    time.sleep(5)
    
# 注册信号处理
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def load_configuration(config_file):
    """加载配置文件"""
    try:
        config_manager = ConfigManager(config_file)
        
        call_list_file = config_manager.get_call_list_file()
        response_file = config_manager.get_response_file()

        #logger.info(f"SIP配置: {sip_config}")
        print(f"呼叫列表文件: {call_list_file}")
        print(f"呼叫响应配置文件: {response_file}")

        # 验证电话号码列表文件存在
        if not os.path.exists(call_list_file):
            print(f"电话号码列表文件不存在: {call_list_file}")
            return None
        
        # 验证呼叫响应配置文件存在
        if not os.path.exists(response_file):
            print(f"呼叫响应配置文件不存在: {response_file}")
            return None
        return config_manager
    except Exception as e:
        print(f"加载配置失败: {e}")
        print(f"详细错误: {traceback.format_exc()}")
        return None

def initialize_services():
    """初始化TTS, Whisper和SIP服务"""
    global sip_caller, services, exit_event, config
    
    try:
        # 初始化TTS引擎
        logger.info("初始化TTS引擎...")
        tts_manager = TTSManager(config.get_tts_cache_dir(), config.get_voice())
        
        # 初始化Whisper转录
        logger.info("初始化Whisper转录...")
        whisper_manager = WhisperManager()
        if not whisper_manager:
            logger.error("Whisper模型初始化失败")
            return None

        sip_config = config.get_sip_config()
        response_manager = ResponseManager(config.get_response_file())
        
        # 初始化SIP客户端
        logger.info(f"初始化SIP客户端: {sip_config['server']}:{sip_config['port']}")
        try:
            sip_caller = SIPCaller(sip_config, tts_manager, whisper_manager, response_manager)
            logger.info("SIP客户端初始化成功")
        except Exception as e:
            logger.error(f"SIP客户端初始化失败: {e}")
            logger.error(f"请检查SIP服务器配置是否正确")
            return None
        
        # 检查SIP客户端是否成功初始化
        if not sip_caller or not sip_caller.acc:
            logger.error("SIP客户端初始化不完整，无法进行呼叫")
            return None

        # 初始化呼叫管理器
        logger.info("初始化呼叫管理器...")
        call_log_file = config.get_call_log_file()
        telegram_config = config.get_telegram_config()
        call_manager = CallManager(sip_caller, tts_manager, whisper_manager, call_log_file, exit_event, telegram_config)
        
        # 存储服务实例以便全局访问
        services = {
            'tts_manager': tts_manager,
            'whisper_manager': whisper_manager,
            'call_manager': call_manager
        }
        
        return services
    except Exception as e:
        logger.error(f"初始化服务失败: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        return None

def prepare_call_list(call_manager, call_list_file):
    """准备要拨打的电话号码列表"""
    try:
        # 加载电话号码列表
        if not call_manager.load_call_list(call_list_file):
            logger.error(f"无法加载电话号码列表: {call_list_file}")
            return None
            
        # 检查电话号码列表是否为空
        if not call_manager.call_list:
            logger.error("电话号码列表为空")
            return None
            
        return call_manager.call_list
    except Exception as e:
        logger.error(f"准备呼叫列表失败: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        return None

def is_working_hours(working_hours):
    """检查当前是否在工作时段内"""
    try:
        if not working_hours.get('enabled', False):
            return True
            
        now = datetime.now()
        current_day = now.weekday()  # 0-6 代表周一到周日
        
        # 检查是否在工作日
        if current_day not in working_hours.get('days', [0, 1, 2, 3, 4, 5]):
            print(f"当前是周{current_day + 1}，非工作日")
            return False
            
        # 将时间字符串转换为datetime对象进行比较
        start_time_str = working_hours.get('start', '12:00')
        end_time_str = working_hours.get('end', '21:00')
        
        # 创建今天的开始和结束时间
        start_time = datetime.strptime(start_time_str, '%H:%M').replace(
            year=now.year, month=now.month, day=now.day)
        end_time = datetime.strptime(end_time_str, '%H:%M').replace(
            year=now.year, month=now.month, day=now.day)
        
        # 如果结束时间小于开始时间，说明跨天，需要调整结束时间
        if end_time < start_time:
            end_time = end_time.replace(day=now.day + 1)
        
        if start_time <= now <= end_time:
            return True
        else:
            print(f"当前时间 {now.strftime('%H:%M')} 不在工作时段 {start_time_str}-{end_time_str} 内")
            return False
            
    except Exception as e:
        print(f"检查工作时段时出错: {e}")
        return False

def process_phone_list(call_list, call_manager, whisper_manager, config):
    """处理电话号码列表"""
    logger.info(f"共 {len(call_list)} 个号码需要处理")
    sip_config = config.get_sip_config()
    whitelist_ips = config.get_whitelist_ips()
    interval = config.get_interval()
    working_hours = sip_config.get('working_hours', {
        'enabled': True,
        'start': '12:00',
        'end': '22:00',
        'days': [0, 1, 2, 3, 4, 5]  # 0-6 代表周一到周日
    })

    i = 0
    max_val = len(call_list)
    while i < max_val:
        # 检查是否请求退出
        if exit_event.is_set():
            logger.info("检测到退出请求，停止拨号")
            break

        if not is_working_hours(working_hours):
            # 当前不是工作时段，等待拨打
            time.sleep(60)
            continue

        # 检查IP是否在白名单中
        current_ip = get_my_ip()
        if current_ip not in whitelist_ips:
             logger.warning(f"当前IP {current_ip} 不在白名单中，等待拨打")
             time.sleep(60)
             continue

        phone = call_list[i]
        i+=1
        logger.info(f"正在处理第 {i}/{len(call_list)} 个号码: {phone}")
        # 拨打电话并等待通话完成
        result = call_manager.make_call(phone)
        call_manager.save_call_result(result)
        play_error = result.get('play_error', False)
        if play_error:
            return False
        time.sleep(interval)
    return True


def cleanup_resources():
    """清理系统资源"""
    global sip_caller
    try:
        # 停止SIP客户端
        if sip_caller:
            sip_caller.stop()
            sip_caller = None
                            
        logger.info("资源清理完成")
    except Exception as e:
        logger.error(f"清理资源时出错: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")

def main():
    """主程序入口点"""
    global exit_event, services, config
    
    try:
        config_file = sys.argv[1] if len(sys.argv) > 1 else 'conf/config98.yaml'
        if not os.path.exists(config_file):
            print(f"配置文件不存在: {config_file}")
            return 1

        # 加载配置
        config = load_configuration(config_file)
        if not config:
            logger.error("无法加载配置，程序退出")
            return 1

        # 清理IP地址中的不可见字符
        current_ip = get_my_ip()
        whitelist_ips = config.get_whitelist_ips()
        if current_ip not in whitelist_ips:
            print(f"当前IP {current_ip} 不在白名单中, 程序退出")
            return 1

        # 初始化日志
        setup_logging(config.get_auto_caller_file())

        # 初始化信号处理
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 初始化服务
        services = initialize_services()
        if not services:
            logger.error("服务初始化失败，程序退出")
            return 1
            
        call_manager = services['call_manager']
        whisper_manager = services['whisper_manager']
            
        # 准备呼叫列表
        call_list = prepare_call_list(call_manager, config.get_call_list_file())
        if not call_list:
            logger.error("呼叫列表为空或加载失败，程序退出")
            return 1

        call_log_file = config.get_call_log_file()
        if os.path.exists(call_log_file):
            with open(call_log_file, 'r', encoding='utf-8') as f:
                csv_reader = csv.reader(f, delimiter='\t')
                next(csv_reader)  # 跳过表头
                called_numbers = []
                for row in csv_reader:
                    if str(row[5]) in ['488', '404', '503', '500', '486']:
                        continue
                    if str(row[3]).startswith('错误') and str(row[5])!='200':
                        continue
                    if str(row[3]).startswith('播放失败'):
                        continue
                    called_numbers.append(row[0])
                # 从call_list中删除已经拨打过的电话号码
                call_list = [number for number in call_list if number not in called_numbers]
                logger.info(f"已拨打过{len(called_numbers)}个号码")
            
        # 处理电话列表
        if process_phone_list(call_list, call_manager, whisper_manager, config):
            logger.info("所有呼叫处理完成")
            return 0
        else:
            logger.info("检测到播放失败，进程退出")
            return 1
        
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        return 1
    finally:
        # 清理资源
        cleanup_resources()
        logger.info("程序已退出")


if __name__ == "__main__":
    main() 