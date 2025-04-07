import os
import logging
import time
import ssl
import whisper
import edge_tts
import traceback

from config_manager import ConfigManager
from tts_manager import TTSManager
from whisper_manager import WhisperManager
from sip_caller import SIPCaller
from call_manager import CallManager

# 禁用全局SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("auto_caller.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("main")

def main():
    """主程序入口"""
    try:
        logger.info("===== 自动电话呼叫系统启动 =====")
        
        # 加载配置
        config_manager = ConfigManager('config.yaml')
        sip_config = config_manager.get_sip_config()
        tts_config = config_manager.get_tts_config()
        call_list_file = config_manager.get_call_list_file()
        call_log_file = config_manager.get_call_log_file()
        
        # 初始化TTS引擎
        logger.info("初始化TTS引擎...")
        tts_manager = TTSManager()
        
        # 初始化Whisper语音识别
        logger.info("初始化Whisper语音识别...")
        whisper_manager = WhisperManager()
        
        # 初始化SIP客户端
        logger.info(f"初始化SIP客户端: {sip_config['server']}:{sip_config['port']}")
        sip_caller = SIPCaller(sip_config)
        
        # 初始化呼叫管理器
        logger.info("初始化呼叫管理器...")
        call_manager = CallManager(sip_caller, tts_manager, whisper_manager)
        
        # 加载电话号码列表
        if not call_manager.load_call_list(call_list_file):
            logger.error(f"无法加载电话号码列表: {call_list_file}")
            return
            
        # 检查TTS文本是否设置
        if not tts_config['text']:
            logger.error("未设置TTS文本，请在配置文件中添加tts_text字段")
            return
            
        # 开始处理呼叫
        logger.info(f"开始处理呼叫，TTS文本: {tts_config['text'][:30]}...")
        call_manager.process_calls(
            tts_config['text'], 
            tts_config['voice'], 
            call_log_file,
            interval=5
        )
        
        logger.info("===== 自动电话呼叫系统结束 =====")
        
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
    finally:
        # 确保SIP服务被正确停止
        if 'sip_caller' in locals():
            sip_caller.stop()
            
if __name__ == "__main__":
    main() 