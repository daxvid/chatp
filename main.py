import os
import logging
import time
import ssl
import whisper
import edge_tts
import traceback
import signal
import sys
from threading import Event

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
        except Exception as e:
            logger.error(f"SIP客户端初始化失败: {e}")
            logger.error(f"请检查SIP服务器配置是否正确")
            return
        
        # 检查SIP客户端是否成功初始化
        if not sip_caller or not hasattr(sip_caller, 'acc') or not sip_caller.acc:
            logger.error("SIP客户端初始化不完整，无法进行呼叫")
            return
            
        # 尝试使用不同格式的URI拨打测试号码
        test_formats = [
            "9196",  # 直接号码
            "sip:9196",  # 简单SIP URI
            f"sip:9196@{sip_config['server']}",  # 带域名的SIP URI
            f"sip:9196@{sip_config['server']}:{sip_config['port']}"  # 带端口的SIP URI
        ]
            
        # 测试拨打回声测试号码
        logger.info("开始拨号测试，尝试多种URI格式...")
        test_success = False
        
        for i, test_uri in enumerate(test_formats):
            if exit_event.is_set():
                break
                
            logger.info(f"测试格式 {i+1}/{len(test_formats)}: {test_uri}")
            try:
                # 修改SIPCaller类的make_call方法，直接使用我们提供的URI
                sip_caller._test_uri = test_uri  # 添加一个属性供调试使用
                test_result = sip_caller.make_call(test_uri, None)
                
                if test_result:
                    logger.info(f"使用格式 '{test_uri}' 拨号测试成功!")
                    test_success = True
                    
                    # 等待几秒观察呼叫状态
                    logger.info("等待10秒观察通话状态...")
                    call_start_time = time.time()
                    
                    for j in range(10):
                        if exit_event.is_set():
                            break
                            
                        if sip_caller.current_call and sip_caller.current_call.isActive():
                            try:
                                ci = sip_caller.current_call.getInfo()
                                logger.info(f"测试呼叫状态 [{j}秒]: 状态={ci.state}, 状态码={ci.lastStatusCode}")
                                
                                # 如果通话已连接超过5秒，可以提前结束测试
                                if ci.state == pj.PJSIP_INV_STATE_CONFIRMED and time.time() - call_start_time > 5:
                                    logger.info("通话已连接，测试成功，提前结束测试")
                                    break
                            except Exception as e:
                                logger.warning(f"获取测试呼叫状态失败: {e}")
                        else:
                            logger.info(f"测试呼叫状态 [{j}秒]: 呼叫不活跃")
                        
                        time.sleep(1)
                    
                    # 挂断通话
                    sip_caller.hangup()
                    logger.info("测试通话已挂断")
                    
                    # 找到成功的格式后，记录并退出测试循环
                    logger.info(f"成功的SIP URI格式: {test_uri}")
                    break
                else:
                    logger.warning(f"使用格式 '{test_uri}' 拨号测试失败")
            except Exception as e:
                logger.error(f"使用格式 '{test_uri}' 拨号测试出错: {e}")
                logger.debug(f"错误详情: {traceback.format_exc()}")
            
            # 确保上一次通话已结束
            sip_caller.hangup()
            time.sleep(2)  # 在尝试下一个格式前等待
            
        if not test_success:
            logger.warning("所有拨号测试格式均失败，但将继续执行...")
        
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
            
if __name__ == "__main__":
    main() 