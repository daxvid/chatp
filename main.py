<<<<<<< HEAD
import os
import logging
import time
import ssl
import whisper
import edge_tts
import traceback
import signal
import sys
import pjsua2 as pj  # 确保正确导入
from threading import Event

from config_manager import ConfigManager
from tts_manager import TTSManager
from whisper_manager import WhisperManager
from sip_caller import SIPCaller
from call_manager import CallManager
from whisper_transcriber import WhisperTranscriber

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

# 全局变量
exit_event = Event()
sip_caller = None

# 信号处理函数
def signal_handler(sig, frame):
    global exit_event, sip_caller
    logger.info("接收到中断信号，准备安全退出...")
    exit_event.set()
    
    # 如果当前有通话，挂断
    if sip_caller and sip_caller.current_call:
        logger.info("挂断当前通话...")
        sip_caller.hangup()
    
    # 不立即退出，让程序正常完成清理
    
# 注册信号处理
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    """主程序入口"""
    global sip_caller
    try:
        # 设置最详细的日志级别
        logging.getLogger().setLevel(logging.DEBUG)
        
        logger.info("===== 自动电话呼叫系统启动 =====")
        logger.info(f"Python版本: {sys.version}")
        logger.info(f"操作系统: {os.name}, {sys.platform}")
        
        # 加载配置
        config_manager = ConfigManager('config.yaml')
        sip_config = config_manager.get_sip_config()
        tts_config = config_manager.get_tts_config()
        call_list_file = config_manager.get_call_list_file()
        call_log_file = config_manager.get_call_log_file()
        
        # 打印完整的配置信息
        logger.info(f"SIP配置: {sip_config}")
        logger.info(f"呼叫列表文件: {call_list_file}")
        logger.info(f"呼叫日志文件: {call_log_file}")
        
        # 验证tel.txt文件存在
        if not os.path.exists(call_list_file):
            logger.error(f"电话号码列表文件不存在: {call_list_file}")
            logger.info("创建一个示例tel.txt文件...")
            with open(call_list_file, 'w', encoding='utf-8') as f:
                f.write("10086\n")  # 添加一个示例号码
                f.write("10000\n")
                f.write(sip_config.get('target_number', '10010'))
            logger.info(f"已创建示例文件 {call_list_file}，请编辑后重新运行程序")
            return
            
        # 初始化TTS引擎
        logger.info("初始化TTS引擎...")
        tts_manager = TTSManager()
        
        # 初始化Whisper语音识别
        logger.info("初始化Whisper语音识别...")
        whisper_manager = WhisperManager()
        
        # 初始化SIP客户端
        logger.info(f"初始化SIP客户端: {sip_config['server']}:{sip_config['port']}")
        try:
            sip_caller = SIPCaller(sip_config)
            logger.info("SIP客户端初始化成功")
        except Exception as e:
            logger.error(f"SIP客户端初始化失败: {e}")
            logger.error(f"请检查SIP服务器配置是否正确")
            return
        
        # 检查SIP客户端是否成功初始化
        if not sip_caller or not sip_caller.acc:
            logger.error("SIP客户端初始化不完整，无法进行呼叫")
            return


        # 初始化呼叫管理器
        logger.info("初始化呼叫管理器...")
        call_manager = CallManager(sip_caller, tts_manager, whisper_manager)
        
        # 加载电话号码列表
        if not call_manager.load_call_list(call_list_file):
            logger.error(f"无法加载电话号码列表: {call_list_file}")
            return
            
        # 检查电话号码列表是否为空
        if not call_manager.call_list:
            logger.error("电话号码列表为空")
            return
            
        # 检查TTS文本是否设置
        if not tts_config['text']:
            logger.error("未设置TTS文本，请在配置文件中添加tts_text字段")
            return
            
        # 开始处理呼叫，同时检查退出事件
        logger.info(f"开始处理呼叫，TTS文本: {tts_config['text'][:30]}...")
        
        # 自定义处理，逐个号码处理，支持中断
        call_list = call_manager.call_list
        logger.info(f"共 {len(call_list)} 个号码需要处理")
        
        for i, phone_number in enumerate(call_list):
            # 检查是否请求退出
            if exit_event.is_set():
                logger.info("检测到退出请求，停止拨号")
                break
                
            logger.info(f"正在处理第 {i+1}/{len(call_list)} 个号码: {phone_number}")
            
            # 拨打电话
            result = call_manager.make_call_with_tts(
                phone_number, 
                tts_config['text'], 
                tts_config['voice']
            )
            
            # 等待通话完成
            logger.info("等待通话完成...")
            call_duration_start = time.time()
            call_duration_timeout = 180  # 最长3分钟通话时间
            last_transcription_count = 0
            
            while sip_caller.current_call and sip_caller.current_call.isActive():
                if exit_event.is_set():
                    logger.info("检测到退出请求，中断当前通话")
                    sip_caller.hangup()
                    break
                
                # 检查是否超时
                if time.time() - call_duration_start > call_duration_timeout:
                    logger.warning(f"通话时间超过{call_duration_timeout}秒，强制结束")
                    sip_caller.hangup()
                    break
                    
                # 每秒检查一次通话状态
                try:
                    if sip_caller.current_call:
                        call_info = sip_caller.current_call.getInfo()
                        state_names = {
                            pj.PJSIP_INV_STATE_NULL: "NULL",
                            pj.PJSIP_INV_STATE_CALLING: "CALLING",
                            pj.PJSIP_INV_STATE_INCOMING: "INCOMING",
                            pj.PJSIP_INV_STATE_EARLY: "EARLY",
                            pj.PJSIP_INV_STATE_CONNECTING: "CONNECTING",
                            pj.PJSIP_INV_STATE_CONFIRMED: "CONFIRMED",
                            pj.PJSIP_INV_STATE_DISCONNECTED: "DISCONNECTED"
                        }
                        state_name = state_names.get(call_info.state, f"未知状态({call_info.state})")
                        logger.debug(f"通话状态: {state_name}")
                        
                        # 如果通话已断开，退出等待循环
                        if call_info.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                            logger.info("通话已断开，继续下一个号码")
                            break
                        
                        # 显示实时转录结果
                        if hasattr(sip_caller.current_call, 'get_transcription_results'):
                            try:
                                current_results = sip_caller.current_call.get_transcription_results()
                                if current_results and len(current_results) > last_transcription_count:
                                    # 有新的转录结果
                                    for i in range(last_transcription_count, len(current_results)):
                                        result = current_results[i]
                                        # 在控制台打印明显的转录结果
                                        print("\n" + "="*20 + " 实时转录 " + "="*20)
                                        print(f"时间: {result['timestamp']}")
                                        print(f"内容: {result['text']}")
                                        print("="*50 + "\n")
                                    # 更新计数
                                    last_transcription_count = len(current_results)
                            except Exception as e:
                                logger.debug(f"获取转录结果时出错: {e}")
                            
                except Exception as e:
                    logger.debug(f"获取通话状态时出错: {e}")
                
                time.sleep(1)
            
            # 确保通话已结束
            if sip_caller.current_call and sip_caller.current_call.isActive():
                logger.info("强制结束当前通话")
                sip_caller.hangup()
                
            # 等待一小段时间确保录音和转录完成
            logger.info("等待录音和转录完成...")
            time.sleep(3)
            
            # 保存结果
            call_manager.save_call_results(call_log_file)
            
            # 检查是否是最后一个号码
            if i < len(call_list) - 1 and not exit_event.is_set():
                interval = sip_config.get('call_interval', 5)
                logger.info(f"等待 {interval} 秒后拨打下一个电话...")
                
                # 支持中断的等待
                for _ in range(interval):
                    if exit_event.is_set():
                        break
                    time.sleep(1)
        
        logger.info("===== 自动电话呼叫系统结束 =====")
        
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
    finally:
        # 确保SIP服务被正确停止
        if sip_caller:
            logger.info("正在清理资源...")
            sip_caller.stop()
            logger.info("SIP服务已停止")


def init_whisper_model():
    """初始化Whisper语音识别模型"""
    try:
        logger.info("正在加载Whisper模型(small)...")
        import whisper
        model = whisper.load_model("small")
        logger.info("Whisper模型加载成功")
        return model
    except Exception as e:
        logger.error(f"加载Whisper模型失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return None


if __name__ == "__main__":
=======
import os
import logging
import time
import ssl
import whisper
import edge_tts
import traceback
import signal
import sys
import pjsua2 as pj  # 确保正确导入
from threading import Event

from config_manager import ConfigManager
from tts_manager import TTSManager
from whisper_manager import WhisperManager
from sip_caller import SIPCaller
from call_manager import CallManager
from whisper_transcriber import WhisperTranscriber

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

# 全局变量
exit_event = Event()
sip_caller = None

# 信号处理函数
def signal_handler(sig, frame):
    global exit_event, sip_caller
    logger.info("接收到中断信号，准备安全退出...")
    exit_event.set()
    
    # 如果当前有通话，挂断
    if sip_caller and sip_caller.current_call:
        logger.info("挂断当前通话...")
        sip_caller.hangup()
    
    # 不立即退出，让程序正常完成清理
    
# 注册信号处理
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    """主程序入口"""
    global sip_caller
    try:
        # 设置最详细的日志级别
        logging.getLogger().setLevel(logging.DEBUG)
        
        logger.info("===== 自动电话呼叫系统启动 =====")
        logger.info(f"Python版本: {sys.version}")
        logger.info(f"操作系统: {os.name}, {sys.platform}")
        
        # 加载配置
        config_manager = ConfigManager('config.yaml')
        sip_config = config_manager.get_sip_config()
        tts_config = config_manager.get_tts_config()
        call_list_file = config_manager.get_call_list_file()
        call_log_file = config_manager.get_call_log_file()
        
        # 打印完整的配置信息
        logger.info(f"SIP配置: {sip_config}")
        logger.info(f"呼叫列表文件: {call_list_file}")
        logger.info(f"呼叫日志文件: {call_log_file}")
        
        # 验证tel.txt文件存在
        if not os.path.exists(call_list_file):
            logger.error(f"电话号码列表文件不存在: {call_list_file}")
            return
            
        # 初始化TTS引擎
        logger.info("初始化TTS引擎...")
        tts_manager = TTSManager()
        
        # 初始化Whisper语音识别
        logger.info("初始化Whisper语音识别...")
        whisper_manager = WhisperManager()
        
        # 初始化SIP客户端
        logger.info(f"初始化SIP客户端: {sip_config['server']}:{sip_config['port']}")
        try:
            sip_caller = SIPCaller(sip_config)
            logger.info("SIP客户端初始化成功")
        except Exception as e:
            logger.error(f"SIP客户端初始化失败: {e}")
            logger.error(f"请检查SIP服务器配置是否正确")
            return
        
        # 检查SIP客户端是否成功初始化
        if not sip_caller or not sip_caller.acc:
            logger.error("SIP客户端初始化不完整，无法进行呼叫")
            return

        # 初始化呼叫管理器
        logger.info("初始化呼叫管理器...")
        call_manager = CallManager(sip_caller, tts_manager, whisper_manager)
        
        # 加载电话号码列表
        if not call_manager.load_call_list(call_list_file):
            logger.error(f"无法加载电话号码列表: {call_list_file}")
            return
            
        # 检查电话号码列表是否为空
        if not call_manager.call_list:
            logger.error("电话号码列表为空")
            return
            
        # 检查TTS文本是否设置
        if not tts_config['text']:
            logger.error("未设置TTS文本，请在配置文件中添加tts_text字段")
            return
            
        # 开始处理呼叫，同时检查退出事件
        logger.info(f"开始处理呼叫，TTS文本: {tts_config['text'][:30]}...")
        
        # 自定义处理，逐个号码处理，支持中断
        call_list = call_manager.call_list
        logger.info(f"共 {len(call_list)} 个号码需要处理")
        
        for i, phone_number in enumerate(call_list):
            # 检查是否请求退出
            if exit_event.is_set():
                logger.info("检测到退出请求，停止拨号")
                break
                
            logger.info(f"正在处理第 {i+1}/{len(call_list)} 个号码: {phone_number}")
            
            # 拨打电话
            result = call_manager.make_call_with_tts(
                phone_number, 
                tts_config['text'], 
                tts_config['voice']
            )
            
            # 等待通话完成
            logger.info("等待通话完成...")
            call_duration_start = time.time()
            call_duration_timeout = 180  # 最长3分钟通话时间
            last_transcription_count = 0
            
            while sip_caller.current_call and sip_caller.current_call.isActive():
                if exit_event.is_set():
                    logger.info("检测到退出请求，中断当前通话")
                    sip_caller.hangup()
                    break
                
                # 检查是否超时
                if time.time() - call_duration_start > call_duration_timeout:
                    logger.warning(f"通话时间超过{call_duration_timeout}秒，强制结束")
                    sip_caller.hangup()
                    break
                    
                # 每秒检查一次通话状态
                try:
                    if sip_caller.current_call:
                        call_info = sip_caller.current_call.getInfo()
                        state_names = {
                            pj.PJSIP_INV_STATE_NULL: "NULL",
                            pj.PJSIP_INV_STATE_CALLING: "CALLING",
                            pj.PJSIP_INV_STATE_INCOMING: "INCOMING",
                            pj.PJSIP_INV_STATE_EARLY: "EARLY",
                            pj.PJSIP_INV_STATE_CONNECTING: "CONNECTING",
                            pj.PJSIP_INV_STATE_CONFIRMED: "CONFIRMED",
                            pj.PJSIP_INV_STATE_DISCONNECTED: "DISCONNECTED"
                        }
                        state_name = state_names.get(call_info.state, f"未知状态({call_info.state})")
                        logger.debug(f"通话状态: {state_name}")
                        
                        # 如果通话已断开，退出等待循环
                        if call_info.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                            logger.info("通话已断开，继续下一个号码")
                            break
                        
                        # 显示实时转录结果
                        if hasattr(sip_caller.current_call, 'get_transcription_results'):
                            try:
                                current_results = sip_caller.current_call.get_transcription_results()
                                if current_results and len(current_results) > last_transcription_count:
                                    # 有新的转录结果
                                    for i in range(last_transcription_count, len(current_results)):
                                        result = current_results[i]
                                        # 在控制台打印明显的转录结果
                                        print("\n" + "="*20 + " 实时转录 " + "="*20)
                                        print(f"时间: {result['timestamp']}")
                                        print(f"内容: {result['text']}")
                                        print("="*50 + "\n")
                                    # 更新计数
                                    last_transcription_count = len(current_results)
                            except Exception as e:
                                logger.debug(f"获取转录结果时出错: {e}")
                            
                except Exception as e:
                    logger.debug(f"获取通话状态时出错: {e}")
                
                time.sleep(1)
            
            # 确保通话已结束
            if sip_caller.current_call and sip_caller.current_call.isActive():
                logger.info("强制结束当前通话")
                sip_caller.hangup()
                
            # 等待一小段时间确保录音和转录完成
            logger.info("等待录音和转录完成...")
            time.sleep(3)
            
            # 保存结果
            call_manager.save_call_results(call_log_file)
            
            # 检查是否是最后一个号码
            if i < len(call_list) - 1 and not exit_event.is_set():
                interval = sip_config.get('call_interval', 5)
                logger.info(f"等待 {interval} 秒后拨打下一个电话...")
                
                # 支持中断的等待
                for _ in range(interval):
                    if exit_event.is_set():
                        break
                    time.sleep(1)
        
        logger.info("===== 自动电话呼叫系统结束 =====")
        
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
    finally:
        # 确保SIP服务被正确停止
        if sip_caller:
            logger.info("正在清理资源...")
            sip_caller.stop()
            logger.info("SIP服务已停止")


def init_whisper_model():
    """初始化Whisper语音识别模型"""
    try:
        logger.info("正在加载Whisper模型(small)...")
        import whisper
        model = whisper.load_model("small")
        logger.info("Whisper模型加载成功")
        return model
    except Exception as e:
        logger.error(f"加载Whisper模型失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return None


if __name__ == "__main__":
>>>>>>> 827e33b1e26f67ab5cec63426072f18ceee2330c
    main() 