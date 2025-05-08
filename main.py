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
import subprocess
import shutil

from config_manager import ConfigManager
from response_manager import ResponseManager
from tts_manager import TTSManager
from whisper_manager import WhisperManager
from sip_caller import SIPCaller
from call_manager import CallManager

# 禁用全局SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

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
        tts_manager = TTSManager()
        
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

def wait_for_interval(interval, exit_event):
    """等待指定的时间间隔，支持中断"""
    logger.info(f"等待 {interval} 秒后拨打下一个电话...")
    for _ in range(interval):
        if exit_event.is_set():
            break
        time.sleep(1)


def process_phone_list(call_list, call_manager, whisper_manager, sip_config):
    """处理电话号码列表"""
    logger.info(f"共 {len(call_list)} 个号码需要处理")
    
    for i, phone in enumerate(call_list):
        # 检查是否请求退出
        if exit_event.is_set():
            logger.info("检测到退出请求，停止拨号")
            break

        logger.info(f"正在处理第 {i+1}/{len(call_list)} 个号码: {phone}")
        # 拨打电话并等待通话完成
        result = call_manager.make_call(phone)
        
        # 保存结果
        call_manager.save_call_result(result)
        
        # 如果不是最后一个号码且未请求退出，等待一段时间
        if i < len(call_list) - 1 and not exit_event.is_set():
            interval = sip_config.get('call_interval', 5)
            wait_for_interval(interval, exit_event)

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
        
        # 获取当前外网IP
        try:
            # 使用 -s 参数让curl静默运行，不显示进度信息
            response = subprocess.check_output(['curl', '-s', 'ifconfig.me'], stderr=subprocess.STDOUT)
            current_ip = response.decode().strip()
            logger.info(f"当前外网IP: {current_ip}")
        except subprocess.CalledProcessError as e:
            logger.error(f"获取外网IP失败: {e.output.decode()}")
            return 1

        # 清理IP地址中的不可见字符
        current_ip = current_ip.strip()
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
                    if row[5] != '488':
                        called_numbers.append(row[0])
                # called_numbers = [row[0] for row in csv_reader]
                # 从call_list中删除已经拨打过的电话号码
                call_list = [number for number in call_list if number not in called_numbers]
                logger.info(f"已拨打过{len(called_numbers)}个号码")
            
        # 处理电话列表
        process_phone_list(call_list, call_manager, whisper_manager, config.get_sip_config())
            
        logger.info("所有呼叫处理完成")
        return 0
        
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