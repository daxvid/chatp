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
            with wave.open(self.voice_file, 'rb') as wf:
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 8000:
                    logger.warning("语音文件不是单声道、16位、8kHz采样率，尝试转换...")
                    self._convert_to_compatible_wav()
                self.voice_data = wf.readframes(wf.getnframes())
                logger.info(f"语音文件加载成功: {self.voice_file}")
        except Exception as e:
            logger.error(f"加载语音文件失败: {e}")
            self.voice_data = None
            
            
    def _convert_to_compatible_wav(self):
        """转换WAV文件为PJSIP兼容格式（单声道、16位、8kHz采样率）"""
        try:
            import subprocess
            temp_file = self.voice_file + '.temp.wav'
            
            # 使用ffmpeg转换
            cmd = [
                'ffmpeg', '-y', 
                '-i', self.voice_file, 
                '-acodec', 'pcm_s16le', 
                '-ar', '8000', 
                '-ac', '1', 
                temp_file
            ]
            
            logger.info(f"转换WAV为兼容格式: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            
            # 替换原始文件
            import os
            os.rename(temp_file, self.voice_file)
            logger.info(f"WAV文件已转换为兼容格式: {self.voice_file}")
            
        except Exception as e:
            logger.error(f"WAV格式转换失败: {e}")
            raise

    def _load_response_file(self):
        """加载响应语音文件"""
        try:    
            with wave.open(self.response_voice_file, 'rb') as wf:
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 8000:
                    logger.warning("响应语音文件不是单声道、16位、8kHz采样率，尝试转换...")
                    self._convert_to_compatible_wav(self.response_voice_file)
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
        """准备实时转录（不再启动线程，由main.py主循环处理）"""
        try:
            # 如果录音文件存在且Whisper模型已加载
            if self.recording_file and self.whisper_model:
                # 创建WhisperTranscriber实例
                if not self.transcriber:
                    self.transcriber = WhisperTranscriber(self.whisper_model)
                
                # 设置实时转录参数，不再启动线程
                self.transcriber.start_realtime_transcription(
                    self.recording_file,
                    response_callback=self.handle_transcription_result,
                    play_response_callback=self.play_response_direct
                )
                logger.info("实时转录参数已准备，将由main.py主循环处理")
                return True
            else:
                logger.error("无法准备转录：录音文件或Whisper模型未准备好")
                return False
        except Exception as e:
            logger.error(f"准备实时转录失败: {e}")
            return False

    def handle_transcription_result(self, text):
        """处理转录结果的回调函数"""
        if text:
            logger.info(f"收到转录结果: {text}")
            # 这里可以添加其他处理逻辑，如关键词匹配等
            self.should_play_response = True
            
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
                        
                        # 启动响应检查线程
                        self.start_response_check_thread()
                
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
                
                # 停止响应检查线程
                if hasattr(self, 'response_check_active'):
                    self.response_check_active = False
                    if hasattr(self, 'response_check_thread') and self.response_check_thread:
                        self.response_check_thread.join(timeout=2)
                
                # 停止录音
                if self.recorder:
                    self.stop_recording()
                    
                    # 转录通话录音
                    self.transcribe_audio()
                    
        except Exception as e:
            logger.error(f"处理呼叫状态变化时出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")

    def start_response_check_thread(self):
        """启动响应检查线程"""
        try:
            self.response_check_active = True
            self.response_check_thread = threading.Thread(
                target=self._response_check_loop,
                daemon=True
            )
            self.response_check_thread.start()
            logger.info("响应检查线程已启动")
            return True
        except Exception as e:
            logger.error(f"启动响应检查线程失败: {e}")
            return False
            
    def _response_check_loop(self):
        """响应检查循环"""
        try:
            check_count = 0
            max_checks = 60  # 30秒
            
            while self.response_check_active and check_count < max_checks:
                check_count += 1
                
                # 简单的标志检查
                if hasattr(self, 'should_play_response') and self.should_play_response:
                    logger.info("检测到should_play_response标志，标记为下一次媒体状态变化时播放")
                    # 将标志保持为True，等待下一次媒体状态变化时播放
                    time.sleep(0.5)
                    continue
                
                time.sleep(0.5)
                
            logger.info("响应检查线程结束")
            
        except Exception as e:
            logger.error(f"响应检查线程出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
        
        self.response_check_active = False

    def play_response_direct(self):
        """直接播放响应音频到通话对方"""
        try:
            if not self.response_voice_file or not os.path.exists(self.response_voice_file):
                logger.error(f"响应语音文件不存在: {self.response_voice_file}")
                return False
                
            logger.info(f"准备播放响应音频到通话对方: {self.response_voice_file}")
            
            # 设置标志，通知onCallMediaState在媒体状态改变时播放
            self.should_play_response = True
            
            # 尝试立即播放，如果可能的话
            try:
                # 获取通话媒体
                audio_media = self.getAudioMedia(-1)
                
                if audio_media:
                    # 创建音频播放器
                    player = pj.AudioMediaPlayer()
                    player.createPlayer(self.response_voice_file)
                    
                    # 播放到通话媒体
                    player.startTransmit(audio_media)
                    logger.info("响应语音已开始播放到通话对方")
                    self.has_played_response = True
                    return True
                else:
                    logger.warning("无法获取音频媒体，将在下一次媒体状态变化时尝试播放")
                    return False
            except Exception as e:
                logger.warning(f"立即播放失败，将在下一次媒体状态改变时尝试: {e}")
                # 不返回错误，而是等待onCallMediaState处理
                return True
                
        except Exception as e:
            logger.error(f"播放响应过程中出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False

    def get_transcription_results(self):
        """获取转录结果，供main.py循环调用"""
        try:
            if hasattr(self, 'transcription_results') and self.transcription_results:
                return self.transcription_results
            else:
                # 如果尚未初始化，创建一个空列表
                self.transcription_results = []
                return self.transcription_results
        except Exception as e:
            logger.error(f"获取转录结果失败: {e}")
            return []
            
    def add_transcription_result(self, text):
        """添加新的转录结果"""
        try:
            if not hasattr(self, 'transcription_results'):
                self.transcription_results = []
                
            # 添加带时间戳的结果
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.transcription_results.append({
                'timestamp': timestamp,
                'text': text
            })
            
            # 同时调用原有的处理回调
            self.handle_transcription_result(text)
            
            return True
        except Exception as e:
            logger.error(f"添加转录结果失败: {e}")
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
            
            # 如果未指定语音文件，但config中提供了语音文件路径，则使用它
            if not voice_file and 'voice_file' in self.config:
                voice_file = self.config['voice_file']
                logger.info(f"使用配置中的语音文件: {voice_file}")
                
            # 如果未指定响应语音文件，且config中有tts_text，则生成语音文件
            if not response_voice_file and 'tts_text' in self.config:                
                try:
                    # 使用TTS管理器生成语音
                    tts_text = self.config['tts_text']
                    logger.info(f"从config.yaml中的tts_text生成语音文件: {tts_text}")
                    
                    # 使用TTS管理器生成语音
                    tts_voice = self.config.get('tts_voice', 'zh-CN-XiaoxiaoNeural')
                    response_voice_file = self.tts_manager.generate_tts_sync(tts_text, tts_voice)
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