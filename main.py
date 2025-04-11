import os
import logging
import time
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

def load_configuration():
    """加载配置文件"""
    try:
        config_manager = ConfigManager('config.yaml')
        sip_config = config_manager.get_sip_config()
        tts_config = config_manager.get_tts_config()
        call_list_file = config_manager.get_call_list_file()
        call_log_file = config_manager.get_call_log_file()
        
        logger.info(f"SIP配置: {sip_config}")
        logger.info(f"呼叫列表文件: {call_list_file}")
        logger.info(f"呼叫日志文件: {call_log_file}")
        
        # 验证电话号码列表文件存在
        if not os.path.exists(call_list_file):
            logger.error(f"电话号码列表文件不存在: {call_list_file}")
            return None
            
        return {
            'config_manager': config_manager,
            'sip_config': sip_config,
            'tts_config': tts_config,
            'call_list_file': call_list_file,
            'call_log_file': call_log_file
        }
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        return None

def initialize_services(sip_config):
    """初始化TTS, Whisper和SIP服务"""
    global sip_caller
    
    try:
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
            return None
        
        # 检查SIP客户端是否成功初始化
        if not sip_caller or not sip_caller.acc:
            logger.error("SIP客户端初始化不完整，无法进行呼叫")
            return None

        # 初始化呼叫管理器
        logger.info("初始化呼叫管理器...")
        call_manager = CallManager(sip_caller, tts_manager, whisper_manager)
        
        return {
            'tts_manager': tts_manager,
            'whisper_manager': whisper_manager,
            'call_manager': call_manager
        }
    except Exception as e:
        logger.error(f"初始化服务失败: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        return None

def generate_tts_voice(call_manager, tts_config):
    """生成TTS语音文件"""
    try:
        logger.info(f"生成语音: '{tts_config['text'][:30]}...'")
        wav_file = call_manager.tts_manager.generate_tts_sync(tts_config['text'], tts_config['voice'])
        if not wav_file:
            logger.error("TTS语音生成失败，无法拨打电话")
            return None
        logger.info(f"语音文件生成成功: {wav_file}")
        return wav_file
    except Exception as e:
        logger.error(f"生成TTS语音失败: {e}")
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

def setup_transcription_env():
    """设置实时转录所需的环境"""
    try:
        segment_dir = "segments"
        os.makedirs(segment_dir, exist_ok=True)
        return segment_dir
    except Exception as e:
        logger.error(f"设置转录环境失败: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        return "segments"  # 返回默认值

def get_call_metadata(sip_caller):
    """获取当前通话的元数据，如录音文件和回调函数"""
    try:
        data = {
            'recording_file': None,
            'response_callback': None,
        }
        
        if sip_caller.current_call:
            if hasattr(sip_caller.current_call, 'recording_file'):
                data['recording_file'] = sip_caller.current_call.recording_file
            if hasattr(sip_caller.current_call, 'handle_transcription_result'):
                data['response_callback'] = sip_caller.current_call.response_callback
                
        return data
    except Exception as e:
        logger.error(f"获取通话元数据失败: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        return {
            'recording_file': None,
            'response_callback': None
        }

def process_audio_chunk(segment_count, segment_dir, recording_file, current_size, whisper_manager, sip_caller, response_callback):
    """处理录音文件的新增数据块"""
    try:
        segment_file = os.path.join(segment_dir, f"segment_{segment_count}.wav")
        
        # 复制整个录音文件
        shutil.copy2(recording_file, segment_file)
        
        # 使用ffmpeg预处理音频，确保格式正确
        processed_file = segment_file #os.path.join(segment_dir, f"processed_{segment_count}.wav")
        
        # 使用ffmpeg规范化音频
        #cmd = [
        #    "ffmpeg", "-y", 
        #    "-i", segment_file, 
        #    "-ar", "16000",  # 采样率16kHz
        #    "-ac", "1",      # 单声道
        #    "-c:a", "pcm_s16le",  # 16位PCM
        #    processed_file
        #]
        #subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        #logger.info(f"音频预处理成功: {processed_file}")
        
        # 检查预处理文件
        if os.path.exists(processed_file) and os.path.getsize(processed_file) > 1000:
            # 转录处理
            text = None
            # 使用WhisperTranscriber的方法进行转录
            if sip_caller.current_call and hasattr(sip_caller.current_call, 'transcriber'):
                text = sip_caller.current_call.transcriber.transcribe_file(processed_file)
            else:
                # 直接使用whisper模型进行转录
                try:
                    result = whisper_manager.model.transcribe(
                        processed_file,
                        language="zh",
                        fp16=False
                    )
                    text = result.get("text", "").strip()
                    if text:
                        logger.info(f"语音识别结果 (段{segment_count}): {text}")
                except Exception as e:
                    logger.error(f"转录尝试失败: {e}")
            
            # 如果成功识别到文本，调用回调
            if text:
                # 如果提供了转录结果回调函数，调用它
                if response_callback:
                    response_callback(text)
        else:
            logger.warning(f"预处理后的音频文件过小或不存在: {processed_file}")
    
        # 清理临时文件
        try:
            if os.path.exists(segment_file):
                os.remove(segment_file)
            if os.path.exists(processed_file):
                os.remove(processed_file)
        except Exception as e:
            logger.warning(f"无法删除临时文件: {e}")
            
        return current_size
    except Exception as e:
        logger.error(f"处理音频块失败: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        return None

def update_transcription_display(sip_caller, last_count):
    """更新转录结果显示"""
    try:
        if hasattr(sip_caller.current_call, 'get_transcription_results'):
            current_results = sip_caller.current_call.get_transcription_results()
            if current_results and len(current_results) > last_count:
                # 有新的转录结果
                for i in range(last_count, len(current_results)):
                    result = current_results[i]
                    # 在控制台打印明显的转录结果
                    print("\n" + "="*20 + " 实时转录 " + "="*20)
                    print(f"时间: {result['timestamp']}")
                    print(f"内容: {result['text']}")
                    print("="*50 + "\n")
                # 更新计数
                return len(current_results)
    except Exception as e:
        logger.debug(f"获取转录结果时出错: {e}")
    
    return last_count

def check_call_state(sip_caller):
    """检查通话状态"""
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
            
            # 如果通话已断开，返回True表示可以继续下一个号码
            if call_info.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                logger.info("通话已断开，继续下一个号码")
                return True
        
        return False
    except Exception as e:
        logger.debug(f"获取通话状态时出错: {e}")
        return False

def wait_for_interval(interval, exit_event):
    """等待指定的时间间隔，支持中断"""
    logger.info(f"等待 {interval} 秒后拨打下一个电话...")
    for _ in range(interval):
        if exit_event.is_set():
            break
        time.sleep(1)

def wait_for_call_completion(call_manager, whisper_manager, timeout=180):
    """等待当前通话完成"""
    logger.info("等待通话完成...")
    call_start_time = time.time()
    last_transcription_count = 0
    
    # 实时转录相关变量
    segment_dir = setup_transcription_env()
    call_metadata = get_call_metadata(sip_caller)
    recording_file = call_metadata['recording_file']
    response_callback = call_metadata['response_callback']
    
    last_size = 0
    last_transcription_time = time.time()
    min_chunk_size = 8000  # 至少8KB新数据才处理
    segment_count = 0
    
    while sip_caller.current_call and sip_caller.current_call.isActive():
        # 检查退出请求
        if exit_event.is_set():
            logger.info("检测到退出请求，中断当前通话")
            sip_caller.hangup()
            break
        
        # 检查通话时间是否超时
        if time.time() - call_start_time > timeout:
            logger.warning(f"通话时间超过{timeout}秒，强制结束")
            sip_caller.hangup()
            break
            
        # 检查通话状态
        if check_call_state(sip_caller):
            break
            
        # 实时转录逻辑
        if recording_file and os.path.exists(recording_file) and whisper_manager.model:
            # 获取当前文件大小
            current_size = os.path.getsize(recording_file)
            
            # 如果文件有显著增长，处理新数据
            size_diff = current_size - last_size
            if size_diff > min_chunk_size:
                segment_count += 1
                logger.info(f"检测到录音文件增长: 段{segment_count}, {last_size} -> {current_size} 字节 (+{size_diff}字节)")
                
                # 确保有足够的间隔让Whisper处理数据
                time_since_last = time.time() - last_transcription_time
                if time_since_last < 1.0:
                    time.sleep(1.0 - time_since_last)
                    
                # 处理新的音频段
                new_size = process_audio_chunk(
                    segment_count, segment_dir, recording_file, current_size,
                    whisper_manager, sip_caller, response_callback
                )
                
                # 更新时间和大小
                last_transcription_time = time.time()
                if new_size is not None:
                    last_size = new_size
                else:
                    last_size = current_size
        
        # 更新转录结果显示
        last_transcription_count = update_transcription_display(sip_caller, last_transcription_count)
        
        # 短暂休眠
        time.sleep(0.5)
    
    # 确保通话已结束
    if sip_caller.current_call and sip_caller.current_call.isActive():
        logger.info("强制结束当前通话")
        sip_caller.hangup()
        
    # 等待一小段时间确保录音和转录完成
    logger.info("等待录音和转录完成...")
    time.sleep(3)

def make_call_and_wait(call_manager, whisper_manager, phone_number, wav_file):
    """拨打电话并等待通话完成"""
    try:
        # 拨打电话
        result = call_manager.make_call_with_tts(phone_number, wav_file)
        
        # 等待通话完成
        wait_for_call_completion(call_manager, whisper_manager)
        
        return True
    except Exception as e:
        logger.error(f"拨打电话或等待通话完成时出错: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        return False

def process_phone_list(call_list, call_manager, whisper_manager, wav_file, call_log_file, sip_config):
    """处理电话号码列表"""
    logger.info(f"共 {len(call_list)} 个号码需要处理")
    
    for i, phone_number in enumerate(call_list):
        # 检查是否请求退出
        if exit_event.is_set():
            logger.info("检测到退出请求，停止拨号")
            break
            
        logger.info(f"正在处理第 {i+1}/{len(call_list)} 个号码: {phone_number}")
        
        # 拨打电话并等待通话完成
        make_call_and_wait(call_manager, whisper_manager, phone_number, wav_file)
        
        # 保存结果
        call_manager.save_call_results(call_log_file)
        
        # 如果不是最后一个号码且未请求退出，等待一段时间
        if i < len(call_list) - 1 and not exit_event.is_set():
            interval = sip_config.get('call_interval', 5)
            wait_for_interval(interval, exit_event)

def cleanup_resources():
    """清理资源"""
    global sip_caller
    if sip_caller:
        logger.info("正在清理资源...")
        sip_caller.stop()
        logger.info("SIP服务已停止")

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
        config = load_configuration()
        if config is None:
            return
        
        # 初始化服务
        services = initialize_services(config['sip_config'])
        if services is None:
            return
        
        # 准备呼叫列表
        call_list = prepare_call_list(services['call_manager'], config['call_list_file'])
        if call_list is None:
            return
        
        # 检查TTS文本是否设置
        if not config['tts_config']['text']:
            logger.error("未设置TTS文本，请在配置文件中添加tts_text字段")
            return
        
        # 生成TTS语音文件
        wav_file = generate_tts_voice(services['call_manager'], config['tts_config'])
        if wav_file is None:
            return
        
        # 处理电话号码列表
        process_phone_list(
            call_list, 
            services['call_manager'], 
            services['whisper_manager'], 
            wav_file, 
            config['call_log_file'], 
            config['sip_config']
        )
        
        logger.info("===== 自动电话呼叫系统结束 =====")
        
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
    finally:
        # 确保资源被正确清理
        cleanup_resources()


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
    main() 