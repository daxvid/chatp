import os
import re
import ssl
import time
import yaml
import socket
import logging
import pjsua2 as pj
import threading
import shutil
import math
import struct
import random
import wave
from datetime import datetime
import concurrent.futures

# 尝试导入常用音频处理库
HAVE_SOUNDFILE = False
HAVE_NUMPY = False
HAVE_SCIPY = False
try:
    import soundfile as sf
    HAVE_SOUNDFILE = True
except ImportError:
    pass

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    pass

try:
    from scipy import signal
    HAVE_SCIPY = True
except ImportError:
    pass

# 引入AudioUtils类
from audio_utils import AudioUtils
# 引入TTSManager
from tts_manager import TTSManager
# 引入WhisperTranscriber
from whisper_transcriber import WhisperTranscriber

# 禁用SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

logger = logging.getLogger("sip")

class SIPCall(pj.Call):
    """SIP通话类，继承自pjsua2.Call"""
    def __init__(self, acc, voice_file=None, whisper_model=None, phone_number=None, response_voice_file=None):
        pj.Call.__init__(self, acc)
        self.voice_file = voice_file
        self.response_voice_file = response_voice_file
        self.voice_data = None
        self.recorder = None
        self.recording_file = None
        self.whisper_model = whisper_model
        self.phone_number = phone_number
        self.audio_port = None
        self.has_played_response = False
        self.should_play_response = False
        self.tts_manager = None
        self.response_configs = None
        self.audio_media = None
        self.ep = None
        self.audio_recorder = None
        self.transcriber = None
        
        if self.voice_file:
            self._load_voice_file()
        if self.response_voice_file:
            self._load_response_file()

        # 获取全局Endpoint实例，提前准备好
        try:
            self.ep = pj.Endpoint.instance()
        except Exception as e:
            logger.error(f"获取Endpoint实例失败: {e}")

    def _load_voice_file(self):
        """加载语音文件"""
        try:
            # 使用AudioUtils确保音频文件为SIP兼容格式
            compatible_file = AudioUtils.ensure_sip_compatible_format(self.voice_file)
            if not compatible_file:
                logger.error(f"无法将语音文件转换为SIP兼容格式: {self.voice_file}")
                self.voice_data = None
                return
                
            self.voice_file = compatible_file
            
            # 加载WAV文件数据
            with wave.open(self.voice_file, 'rb') as wf:
                self.voice_data = wf.readframes(wf.getnframes())
                logger.info(f"语音文件加载成功: {self.voice_file}")
        except Exception as e:
            logger.error(f"加载语音文件失败: {e}")
            self.voice_data = None
            
    def _load_response_file(self):
        """加载响应语音文件"""
        try:
            # 使用AudioUtils确保音频文件为SIP兼容格式
            compatible_file = AudioUtils.ensure_sip_compatible_format(self.response_voice_file)
            if not compatible_file:
                logger.error(f"无法将响应语音文件转换为SIP兼容格式: {self.response_voice_file}")
                return
                
            self.response_voice_file = compatible_file
            logger.info(f"响应语音文件加载成功: {self.response_voice_file}")
        except Exception as e:
            logger.error(f"加载响应语音文件失败: {e}")

    def start_recording(self, phone_number):
        """开始录音"""
        try:
            # 如果已经有录音器和录音文件，则不再创建
            if self.recorder or self.audio_recorder:
                logger.info(f"录音器已存在，不再创建")
                return True
                
            # 创建recordings目录
            recordings_dir = "recordings"
            os.makedirs(recordings_dir, exist_ok=True)
            
            # 清理电话号码中的特殊字符，只保留数字
            clean_number = ''.join(filter(str.isdigit, phone_number))
            
            # 创建录音文件名，格式：电话号码_日期时间.wav
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{clean_number}_{timestamp}.wav"
            self.recording_file = os.path.join(recordings_dir, filename)
            
            logger.info(f"创建录音文件: {self.recording_file}")
            
            # 直接创建录音器，但尝试获取媒体录音需要放在onCallMediaState
            try:
                # 创建录音器实例
                self.recorder = pj.AudioMediaRecorder()
                self.recorder.createRecorder(self.recording_file)
                logger.info(f"录音设备创建成功: {self.recording_file}")
                
                # 获取当前音频媒体 - 尝试在这里就连接，如果成功最好
                try:
                    audio_media = self.getAudioMedia(-1)
                    if audio_media:
                        audio_media.startTransmit(self.recorder)
                        logger.info(f"已立即开始录音: {self.recording_file}")
                    else:
                        logger.info(f"无法获取音频媒体，将在媒体状态变化时开始录音")
                except Exception as e:
                    logger.info(f"无法立即连接音频媒体，将在媒体状态变化时开始录音: {e}")
            except Exception as e:
                logger.error(f"创建录音设备失败: {e}")
                self.recording_file = None
                self.recorder = None
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"录音准备失败: {e}")
            self.recording_file = None
            self.recorder = None
            return False
    
    def onCallMediaState(self, prm):
        """处理呼叫媒体状态改变事件"""
        try:
            ci = self.getInfo()
            logger.info(f"呼叫媒体状态改变，当前呼叫状态: {ci.stateText}")
            
            # 尝试获取音频媒体
            try:
                self.audio_media = self.getAudioMedia(-1)
                
                if not self.audio_media:
                    logger.error("无法获取音频媒体")
                    return
                    
                logger.info("成功获取音频媒体")
                
                # 检查是否需要播放响应语音
                if hasattr(self, 'should_play_response') and self.should_play_response:
                    self.should_play_response = False  # 重置标志
                    
                    # 如果有响应语音文件，播放它
                    if self.response_voice_file and os.path.exists(self.response_voice_file):
                        try:
                            logger.info(f"播放响应语音: {self.response_voice_file}")
                            
                            # 创建音频播放器
                            player = pj.AudioMediaPlayer()
                            player.createPlayer(self.response_voice_file)
                            
                            # 播放到音频媒体
                            player.startTransmit(self.audio_media)
                            logger.info("响应语音播放已开始")
                        except Exception as e:
                            logger.error(f"播放响应语音失败: {e}")
                            import traceback
                            logger.error(f"详细错误: {traceback.format_exc()}")
                
                # 处理录音 - 检查是否已经有录音器但尚未连接到音频媒体
                if self.recorder and not self.audio_recorder:
                    try:
                        # 连接现有录音器到音频媒体
                        logger.info(f"连接音频媒体到已有录音设备: {self.recording_file}")
                        self.audio_media.startTransmit(self.recorder)
                        # 记录录音器以便后续使用
                        self.audio_recorder = self.recorder
                        logger.info(f"开始录音: {self.recording_file}")
                    except Exception as e:
                        logger.error(f"连接录音设备失败: {e}")
                        import traceback
                        logger.error(f"详细错误: {traceback.format_exc()}")
                
                # 如果有语音文件需要播放
                if self.voice_file and os.path.exists(self.voice_file):
                    try:
                        # 创建播放器
                        player = pj.AudioMediaPlayer()
                        player.createPlayer(self.voice_file)
                        
                        # 开始传输到呼叫的音频媒体
                        player.startTransmit(self.audio_media)
                        logger.info(f"开始播放语音文件: {self.voice_file}")
                    except Exception as e:
                        logger.error(f"播放语音文件失败: {e}")
                        import traceback
                        logger.error(f"详细错误: {traceback.format_exc()}")
            except Exception as e:
                logger.error(f"处理音频媒体时出错: {e}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
                
        except Exception as e:
            logger.error(f"处理呼叫媒体状态改变时出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            
    def stop_recording(self):
        """停止录音"""
        try:
            if self.audio_recorder:
                # 停止录音
                self.audio_recorder = None
                logger.info(f"录音已停止: {self.recording_file}")
                return True
            elif self.recorder:
                # 可能是创建了录音器但尚未连接到音频媒体
                self.recorder = None
                logger.info(f"录音已停止 (录音器未连接): {self.recording_file}")
                return True
            return False
        except Exception as e:
            logger.error(f"停止录音失败: {e}")
            return False
    
    def start_realtime_transcription_thread(self):
        """启动实时转录线程"""
        try:
            # 如果录音文件存在且Whisper模型已加载
            if self.recording_file and self.whisper_model:
                # 创建WhisperTranscriber实例
                if not self.transcriber:
                    self.transcriber = WhisperTranscriber(self.whisper_model)
                
                # 启动实时转录，并设置回调函数
                self.transcriber.start_realtime_transcription(
                    self.recording_file,
                    response_callback=self.handle_transcription_result,
                    play_response_callback=self.play_response_direct
                )
                logger.info("实时转录线程已启动")
                
                # 启动一个新线程来处理转录队列
                self.start_transcription_queue_processor()
                
                return True
            else:
                logger.error("无法启动转录：录音文件或Whisper模型未准备好")
                return False
        except Exception as e:
            logger.error(f"启动实时转录线程失败: {e}")
            return False

    def start_transcription_queue_processor(self):
        """启动转录队列处理器线程"""
        try:
            self.queue_processor_active = True
            self.queue_processor_thread = threading.Thread(
                target=self._transcription_queue_processor_loop,
                daemon=True
            )
            self.queue_processor_thread.start()
            logger.info("转录队列处理线程已启动")
            return True
        except Exception as e:
            logger.error(f"启动转录队列处理线程失败: {e}")
            self.queue_processor_active = False
            return False

    def _transcription_queue_processor_loop(self):
        """转录队列处理循环"""
        try:
            logger.info("开始转录队列处理循环")
            check_interval = 0.5  # 检查队列的时间间隔
            min_silence_before_response = 3.0  # 检测到多少秒静音后开始响应
            last_transcription_time = 0
            response_triggered = False
            
            while self.queue_processor_active:
                # 检查转录器是否还在运行
                if not hasattr(self, 'transcriber') or not self.transcriber:
                    logger.warning("转录器不存在，退出队列处理循环")
                    break
                    
                # 检查是否有新的转录结果
                if self.transcriber.has_new_transcription():
                    # 获取所有新转录结果
                    new_texts = self.transcriber.get_all_transcriptions()
                    if new_texts:
                        # 记录收到新转录的时间
                        last_transcription_time = time.time()
                        # 记录转录内容
                        for text in new_texts:
                            logger.info(f"从队列获取转录结果: {text}")
                            # 在这里可以对接收到的转录结果进行处理，如保存到文件等
                        
                        # 重置响应触发标志
                        response_triggered = False
                
                # 检查是否需要播放响应
                # 策略：如果一段时间内没有新的转录结果，认为对方说话暂停，此时播放响应
                if not response_triggered and last_transcription_time > 0:
                    time_since_last = time.time() - last_transcription_time
                    if time_since_last >= min_silence_before_response:
                        logger.info(f"检测到 {time_since_last:.1f}秒 没有新转录，准备播放响应")
                        # 播放响应
                        self.play_response_direct()
                        # 标记已触发响应
                        response_triggered = True
                        # 重置最后转录时间
                        last_transcription_time = 0
                
                # 短暂休眠
                time.sleep(check_interval)
                
            logger.info("转录队列处理循环结束")
        except Exception as e:
            logger.error(f"转录队列处理循环出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
        
        self.queue_processor_active = False

    def handle_transcription_result(self, text):
        """处理转录结果的回调函数"""
        if text:
            logger.info(f"收到对方语音转录结果: '{text}'")
            
            # 记录对方的语音内容，可用于日志或后续分析
            if not hasattr(self, 'transcription_history'):
                self.transcription_history = []
            self.transcription_history.append(text)
            
            # 这里不再直接设置播放标志，而是让队列处理器决定何时播放响应
            # self.should_play_response = True

    def transcribe_audio(self):
        """使用Whisper转录录音文件"""
        try:
            if not self.whisper_model:
                logger.error("Whisper模型未加载，无法进行语音识别")
                return None
            
            if not self.transcriber:
                self.transcriber = WhisperTranscriber(self.whisper_model)
                
            if self.recording_file and os.path.exists(self.recording_file):
                return self.transcriber.transcribe_file(self.recording_file)
            else:
                logger.warning(f"录音文件不存在: {self.recording_file}")
                return None
        except Exception as e:
            logger.error(f"转录录音文件失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
            
    def play_response_after_speech(self):
        """在对方说完话后播放响应语音"""
        if self.has_played_response:
            logger.info("已经播放过响应，不再重复播放")
            return
            
        try:
            logger.info("准备播放响应语音")
            # 等待一小段时间，确保对方说完
            time.sleep(0.5)
            
            if not self.response_voice_file or not os.path.exists(self.response_voice_file):
                logger.warning(f"响应语音文件不存在或未指定: {self.response_voice_file}")
                return
                
            # 创建音频播放器
            player = pj.AudioMediaPlayer()
            logger.info(f"尝试播放响应语音文件: {self.response_voice_file}")
            
            # 加载并检查语音文件
            try:
                player.createPlayer(self.response_voice_file)
                logger.info("响应语音播放器已创建")
            except Exception as e:
                logger.error(f"创建响应播放器失败: {e}")
                return
                
            # 获取通话媒体
            try:
                audio_stream = self.getAudioMedia(-1)
                logger.info("成功获取音频媒体")
            except Exception as e:
                logger.error(f"获取音频媒体失败: {e}")
                logger.error("响应语音播放功能不可用")
                return
            
            # 开始传输音频
            player.startTransmit(audio_stream)
            logger.info("开始播放响应语音，音频传输已启动")
            self.has_played_response = True
            
        except Exception as e:
            logger.error(f"播放响应语音过程中出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
    
    def onCallState(self, prm):
        """呼叫状态改变时的回调函数"""
        try:
            ci = self.getInfo()
            state_names = {
                pj.PJSIP_INV_STATE_NULL: "NULL",
                pj.PJSIP_INV_STATE_CALLING: "CALLING",
                pj.PJSIP_INV_STATE_INCOMING: "INCOMING",
                pj.PJSIP_INV_STATE_EARLY: "EARLY",
                pj.PJSIP_INV_STATE_CONNECTING: "CONNECTING",
                pj.PJSIP_INV_STATE_CONFIRMED: "CONFIRMED",
                pj.PJSIP_INV_STATE_DISCONNECTED: "DISCONNECTED"
            }
            state_name = state_names.get(ci.state, f"未知状态({ci.state})")
            
            logger.info(f"呼叫状态改变: {state_name}, 状态码: {ci.lastStatusCode}, 原因: {ci.lastReason}")
            
            if ci.state == pj.PJSIP_INV_STATE_CALLING:
                logger.info("正在呼叫中...")
                
            elif ci.state == pj.PJSIP_INV_STATE_EARLY:
                logger.info("对方电话开始响铃...")
                
            elif ci.state == pj.PJSIP_INV_STATE_CONNECTING:
                logger.info("正在建立连接...")
                
            elif ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
                logger.info("通话已接通")
                
                # 如果有指定电话号码，启动录音
                if self.phone_number:
                    # 启动录音
                    self.start_recording(self.phone_number)
                    
                    # 在录音启动后，直接开始实时转录
                    if self.whisper_model and self.recording_file:
                        logger.info("初始化实时语音转录...")
                        # 启动transcriber_thread
                        self.start_realtime_transcription_thread()
                
            elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                logger.info(f"通话已结束: 状态码={ci.lastStatusCode}, 原因={ci.lastReason}")
                
                # 停止音频传输
                try:
                    if hasattr(self, 'audio_media') and self.audio_media:
                        if hasattr(self, 'audio_recorder') and self.audio_recorder:
                            self.audio_media.stopTransmit(self.audio_recorder)
                except Exception as e:
                    logger.error(f"停止音频传输时出错: {e}")
                
                # 停止实时语音转录
                if hasattr(self, 'transcriber') and self.transcriber:
                    logger.info("停止实时语音转录")
                    self.transcriber.stop_transcription()
                
                # 停止转录队列处理器
                if hasattr(self, 'queue_processor_active'):
                    self.queue_processor_active = False
                    if hasattr(self, 'queue_processor_thread') and self.queue_processor_thread:
                        self.queue_processor_thread.join(timeout=2)
                
                # 停止录音
                if self.recorder:
                    self.stop_recording()
                    
                    # 转录通话录音
                    self.transcribe_audio()
                    
                # 保存转录历史记录
                self.save_transcription_history()
                
        except Exception as e:
            logger.error(f"处理呼叫状态变化时出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")

    def play_response_direct(self):
        """通过SIP通话直接播放响应文件给对方听"""
        try:
            # 如果已经播放过响应，检查是否允许重复播放
            if self.has_played_response:
                # 默认不允许重复播放
                logger.info("已经播放过响应，不再重复播放")
                return False
            
            if not self.response_voice_file or not os.path.exists(self.response_voice_file):
                logger.error(f"响应语音文件不存在: {self.response_voice_file}")
                return False
                
            logger.info(f"尝试通过SIP通话播放响应: {self.response_voice_file}")
            
            # 检查音频媒体是否可用
            if not hasattr(self, 'audio_media') or not self.audio_media:
                # 尝试获取音频媒体
                try:
                    self.audio_media = self.getAudioMedia(-1)
                    if not self.audio_media:
                        logger.error("无法获取音频媒体，无法播放响应")
                        return False
                    logger.info("成功获取音频媒体")
                except Exception as e:
                    logger.error(f"获取音频媒体失败: {e}")
                    return False
            
            # 创建音频播放器
            try:
                # 增加响应音量 (可选)
                # enhanced_voice_file = AudioUtils.enhance_audio_volume(self.response_voice_file, 1.5)
                # play_file = enhanced_voice_file
                play_file = self.response_voice_file
                
                player = pj.AudioMediaPlayer()
                player.createPlayer(play_file)
                logger.info(f"音频播放器创建成功")
                
                # 开始传输到呼叫的音频媒体
                player.startTransmit(self.audio_media)
                logger.info(f"开始通过SIP播放响应语音")
                
                # 标记为已播放响应
                self.has_played_response = True
                
                return True
            except Exception as e:
                logger.error(f"创建音频播放器或播放失败: {e}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
                
                # 设置标志以在下一次媒体状态变化时尝试播放
                self.should_play_response = True
                return False
                
        except Exception as e:
            logger.error(f"播放响应过程中出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False

    def save_transcription_history(self, output_path=None):
        """将转录历史记录保存到文件
        
        Args:
            output_path: 输出文件路径，如果为None则自动生成
            
        Returns:
            bool: 是否成功保存
        """
        try:
            if not hasattr(self, 'transcription_history') or not self.transcription_history:
                logger.warning("没有转录历史记录可保存")
                return False
            
            # 如果未指定输出路径，则使用录音文件名加上_transcript.txt
            if not output_path and self.recording_file:
                output_path = f"{os.path.splitext(self.recording_file)[0]}_transcript.txt"
            elif not output_path:
                # 如果没有录音文件，则使用时间戳
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"transcript_{timestamp}.txt"
            
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            # 写入文件
            with open(output_path, 'w', encoding='utf-8') as f:
                # 添加时间戳作为标题
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                phone_info = f"电话：{self.phone_number}" if self.phone_number else ""
                f.write(f"=== 通话转录 {timestamp} {phone_info} ===\n\n")
                
                # 写入每条转录记录
                for i, text in enumerate(self.transcription_history, 1):
                    f.write(f"{i}. {text}\n")
                
            logger.info(f"转录历史已保存到: {output_path}")
            return True
        except Exception as e:
            logger.error(f"保存转录历史失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False

class SIPCaller:
    """SIP呼叫管理类"""
    def __init__(self, sip_config):
        self.config = sip_config
        self.ep = None
        self.acc = None
        self.current_call = None
        self.phone_number = None
        self.whisper_model = None
        self.response_configs = self._load_response_configs()
        
        # 初始化TTS管理器
        self.tts_manager = TTSManager()
        
        # 初始化PJSIP
        self._init_pjsua2()

    def _init_pjsua2(self):
        """初始化PJSIP"""
        try:
            # 创建Endpoint
            self.ep = pj.Endpoint()
            self.ep.libCreate()

            # 初始化库
            ep_cfg = pj.EpConfig()
            # 禁用SSL证书验证
            ep_cfg.uaConfig.verifyServerCert = False
            self.ep.libInit(ep_cfg)

            # 创建传输
            sipTpConfig = pj.TransportConfig()
            sipTpConfig.port = self.config.get('bind_port', 6000)
            self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, sipTpConfig)

            # 启动库
            logger.info("正在启动PJSIP库...")
            self.ep.libStart()

            # 创建账户配置
            acc_cfg = pj.AccountConfig()
            acc_cfg.idUri = f"sip:{self.config['username']}@{self.config['server']}:{self.config['port']}"
            acc_cfg.regConfig.registrarUri = f"sip:{self.config['server']}:{self.config['port']}"
            acc_cfg.sipConfig.authCreds.append(
                pj.AuthCredInfo(
                    "digest",
                    "*",
                    self.config['username'],
                    0,
                    self.config['password']
                )
            )

            # 创建账户
            self.acc = pj.Account()
            self.acc.create(acc_cfg)

            # 等待注册完成
            max_wait = 30  # 最多等待30秒
            wait_start = time.time()
            while self.acc.getInfo().regStatus != pj.PJSIP_SC_OK:
                if time.time() - wait_start > max_wait:
                    raise Exception(f"SIP注册超时，当前状态: {self.acc.getInfo().regStatus}")
                logger.info(f"等待SIP注册完成，状态: {self.acc.getInfo().regStatus}...")
                time.sleep(0.5)

            logger.info("SIP客户端初始化成功")
        except pj.Error as e:
            logger.error(f"初始化PJSIP失败: {e}")
            raise

    def make_call(self, number, voice_file=None, response_voice_file=None):
        """拨打电话并播放语音"""
        try:
            if self.current_call:
                logger.warning("已有通话在进行中")
                return False

            # 清理数据
            self.phone_number = number.strip()
            logger.info(f"=== 开始拨号 ===")
            logger.info(f"目标号码: {self.phone_number}")
            
            # 构建SIP URI
            sip_uri = f"sip:{self.phone_number}@{self.config.get('server', '')}:{self.config.get('port', '')}"
            logger.info(f"SIP URI: {sip_uri}")
            logger.info(f"SIP账户: {self.config.get('username', '')}@{self.config.get('server', '')}:{self.config.get('port', '')}")
            
            # 如果未指定响应语音文件，且config中有tts_text，则生成语音文件
            if not response_voice_file and 'tts_text' in self.config:                
                try:
                    # 使用TTS管理器生成语音
                    tts_text = self.config['tts_text']
                    logger.info(f"从config.yaml中的tts_text生成语音文件: {tts_text}")
                    
                    # 使用TTS管理器生成语音
                    tts_voice = self.config.get('tts_voice', 'zh-CN-XiaoxiaoNeural')
                    response_voice_file = self.tts_manager.generate_tts_sync(tts_text, tts_voice)
                    logger.info(f"TTS语音生成成功: {response_voice_file}")
                except Exception as e:
                    logger.error(f"TTS语音生成失败: {e}")
                    import traceback
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    
            # 记录语音文件信息
            if voice_file:
                logger.info(f"语音文件: {voice_file}")
            if response_voice_file:
                logger.info(f"响应语音文件: {response_voice_file}")
            
            # 创建通话对象，并传入电话号码和响应语音文件
            call = SIPCall(self.acc, voice_file, self.whisper_model, number, response_voice_file)
            # 传递tts_manager和response_configs到通话对象
            call.tts_manager = self.tts_manager
            call.response_configs = self.response_configs
            
            # 设置呼叫参数
            call_param = pj.CallOpParam(True)
            
            # 发送拨号请求
            logger.info(f"发送拨号请求: {sip_uri}")
            call.makeCall(sip_uri, call_param)
            
            # 更新当前通话
            self.current_call = call
            self.phone_number = number
            
            logger.info("拨号请求已发送")
            logger.info("等待呼叫状态变化...")
            
            return True
            
        except Exception as e:
            logger.error(f"拨打电话失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False

    def hangup(self):
        """挂断当前通话"""
        try:
            if self.current_call:
                call_prm = pj.CallOpParam()
                self.current_call.hangup(call_prm)
                self.current_call = None
                logger.info("通话已挂断")
                return True
            else:
                logger.warning("没有正在进行的通话")
                return False
        except pj.Error as e:
            logger.error(f"挂断通话失败: {e}")
            return False

    def stop(self):
        """停止PJSIP"""
        try:
            if self.acc:
                try:
                    # 使用正确的方法删除账户
                    self.acc.setRegistration(False)
                    time.sleep(1)  # 等待注销完成
                    self.acc = None
                except Exception as e:
                    logger.warning(f"删除账户时出错: {e}")
                    self.acc = None
            if self.ep:
                try:
                    self.ep.libDestroy()
                except Exception as e:
                    logger.warning(f"销毁PJSIP库时出错: {e}")
                    self.ep = None
            logger.info("SIP服务已停止")
        except Exception as e:
            logger.error(f"停止SIP服务失败: {e}")
            self.acc = None
            self.ep = None

    def set_whisper_model(self, model):
        """设置Whisper模型"""
        self.whisper_model = model
        
    def _load_response_configs(self):
        """加载回复配置"""
        try:
            # 尝试从config中读取回复规则
            response_configs = {}
            
            # 如果config中包含response_rules，则加载
            if 'response_rules' in self.config:
                response_configs['rules'] = self.config['response_rules']
                
            # 默认回复
            if 'default_response' in self.config:
                response_configs['default_response'] = self.config['default_response']
            else:
                response_configs['default_response'] = "谢谢您的来电，我们已收到您的信息。"
                
            # TTS语音
            if 'tts_voice' in self.config:
                response_configs['tts_voice'] = self.config['tts_voice']
            else:
                response_configs['tts_voice'] = "zh-CN-XiaoxiaoNeural"
                
            logger.info(f"已加载回复配置: {len(response_configs.get('rules', []))}条规则")
            return response_configs
            
        except Exception as e:
            logger.error(f"加载回复配置失败: {e}")
            # 返回一个包含默认配置的字典
            return {
                'default_response': "谢谢您的来电，我们已收到您的信息。",
                'tts_voice': "zh-CN-XiaoxiaoNeural"
            } 