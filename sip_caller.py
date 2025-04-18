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
import traceback
import pydub
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
# 引入WhisperManager
from whisper_manager import WhisperManager
# 引入ResponseManager
from response_manager import ResponseManager
from fix_wav_in_place import fix_wav_file_in_place

# 禁用SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

logger = logging.getLogger("sip")

class CustomAudioMediaPlayer(pj.AudioMediaPlayer):
    """自定义音频播放器，用于处理播放完成回调"""
    def __init__(self):
        super().__init__()
        self.on_eof_callback = None
        
    def setEofCallback(self, callback):
        """设置播放完成回调函数"""
        self.on_eof_callback = callback
        
    def onEof2(self):
        """播放完成时的回调函数"""
        if self.on_eof_callback:
            self.on_eof_callback()

class SIPCall(pj.Call):
    """SIP通话类，继承自pjsua2.Call"""
    def __init__(self, acc, whisper_manager=None, phone_number=None):
        pj.Call.__init__(self, acc)
        self.recorder = None
        self.recording_file = None
        self.whisper_manager = whisper_manager
        self.phone_number = phone_number
        self.audio_port = None
        self.tts_manager = None
        self.response_manager = None
        self.audio_media = None
        self.ep = None
        self.audio_recorder = None
        self.player = None
        self.chunks_size = 0     # 已保存的音频段数量
        self.file_list = list()  # 已分段的对话文件列表
        self.talk_list = list()  # 已转录的文本内容
        # 通话结果数据
        self.call_result = {
            'phone_number': phone_number,
            'call_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': '未接通',
            'duration': '',
            'recording': '',
            'transcription': '',
            'start_time': datetime.now(),
            'end_time': None
        }
    

        # 获取全局Endpoint实例，提前准备好
        try:
            self.ep = pj.Endpoint.instance()
        except Exception as e:
            logger.error(f"获取Endpoint实例失败: {e}")
            
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
            
            # 直接创建录音器，但尝试获取媒体录音需要放在onCallMediaState
            try:
                # 创建录音器实例
                self.recorder = pj.AudioMediaRecorder()
                self.recorder.createRecorder(self.recording_file)
                logger.info(f"录音创建成功: {self.recording_file}")
                
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
                        logger.error(f"详细错误: {traceback.format_exc()}")
                
            except Exception as e:
                logger.error(f"处理音频媒体时出错: {e}")
                logger.error(f"详细错误: {traceback.format_exc()}")
                
        except Exception as e:
            logger.error(f"处理呼叫媒体状态改变时出错: {e}")
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
    

    def response_callback(self, text):
        """处理转录结果的回调函数"""
        if text:
            logger.info(f"收到转录结果: {text}")
            # 使用ResponseManager获取回复
            if self.response_manager:
                response_text = self.response_manager.get_response(text)
                if response_text:
                    logger.info(f"匹配到回复: {response_text}")
                    # 使用TTS生成语音
                    if self.tts_manager:
                        # 生成TTS文件
                        voice_file = self.tts_manager.generate_tts_sync(response_text)
                        if voice_file and os.path.exists(voice_file):
                            self.play_response_direct(voice_file)
                        else:
                            logger.error(f"生成TTS文件失败")
                    else:
                        logger.error(f"TTS管理器未初始化")
                else:
                    logger.info(f"没有匹配到回复规则")
            else:
                logger.info(f"ResponseManager未初始化")

    def transcribe_audio(self):
        """使用Whisper转录录音文件"""
        try:    
            result = self.whisper_manager.transcribe_and_wait_result(self.recording_file)
            if result:
                return result.get("text", "").strip()
            else:
                logger.warning("无法获取转录结果")
                return None
                
        except Exception as e:
            logger.error(f"转录录音文件失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
            

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
                # 更新通话状态为已接通
                self.call_result['status'] = '接通'
                
                # 如果有指定电话号码，启动录音
                if self.phone_number:
                    self.start_recording(self.phone_number)
                
            elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                logger.info(f"通话已结束: 状态码={ci.lastStatusCode}, 原因={ci.lastReason}")
                
                # 记录通话结束时间
                self.call_result['end_time'] = datetime.now()
                
                # 如果之前标记为接通，则计算通话时长
                if self.call_result['status'] == '接通':
                    duration = (self.call_result['end_time'] - self.call_result['start_time']).total_seconds()
                    self.call_result['duration'] = f"{duration:.1f}秒"
                
                # 停止音频传输
                try:
                    if hasattr(self, 'audio_media') and self.audio_media:
                        if hasattr(self, 'audio_recorder') and self.audio_recorder:
                            self.audio_media.stopTransmit(self.audio_recorder)
                except Exception as e:
                    logger.error(f"停止音频传输时出错: {e}")
                
                # 停止录音
                if self.recorder:
                    self.stop_recording()
                    
                    # 转录通话录音并更新结果
                    transcription = self.transcribe_audio()
                    if transcription:
                        self.call_result['transcription'] = transcription
                        logger.info(f"转录结果: {transcription[:50]}...")
                    else:
                        logger.warning("无法获取转录结果")
                
                # 更新录音文件路径
                if hasattr(self, 'recording_file') and self.recording_file:
                    self.call_result['recording'] = self.recording_file
                    
                logger.info("通话已挂断")
                
        except Exception as e:
            logger.error(f"处理呼叫状态变化时出错: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
         
    def play_response_direct(self, voice_file=None):
        """直接播放响应音频到通话对方"""
        try:
            if not os.path.exists(voice_file):
                logger.error(f"响应语音文件不存在: {voice_file}")
                return False

            # 停止当前播放
            if self.player:
                self.player.stopTransmit(self.audio_media)
                self.player = None
            
            # 尝试立即播放，如果可能的话
            try:
                # 获取通话媒体
                audio_media = self.getAudioMedia(-1)
                if audio_media:
                    # 创建自定义音频播放器
                    player = CustomAudioMediaPlayer()
                    # 使用PJMEDIA_FILE_NO_LOOP标志创建播放器
                    player.createPlayer(voice_file, pj.PJMEDIA_FILE_NO_LOOP)
                    
                    # 注册播放完成回调
                    def on_playback_complete():
                        player.stopTransmit(audio_media)
                        logger.info(f"结束播放语音: {voice_file}")

                    player.setEofCallback(on_playback_complete)
                    # 播放到通话媒体
                    player.startTransmit(audio_media)
                    logger.info(f"开始播放语音: {voice_file}")
                    self.player = player
                    self.audio_media = audio_media
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
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False

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

    def is_active(self):
        """检查通话是否活跃"""
        try:
            if not self:
                return False
                
            ci = self.getInfo()
            return ci.state != pj.PJSIP_INV_STATE_DISCONNECTED
        except:
            return False

    def voice_check(self):
        # 语音分段逻辑,将录音文件分段,每段至少800ms,每段结束时计算RMS值,如果低于-50 dBFS阈值,认为是静音,则保存该段,否则停止分段
        recording_file = self.recording_file
        if not (recording_file and os.path.exists(recording_file)):
            return
        file_size = os.path.getsize(recording_file)
        if file_size < 16*1024: 
            logger.info(f"录音文件太小{file_size}字节, 不进行处理: {recording_file}")
            return

        start_time = datetime.now()
        base_name, ext = os.path.splitext(recording_file)
        temp_file = f"{base_name}_tmp{ext}"
        if os.path.exists(temp_file):
            os.remove(temp_file)

        shutil.copy(recording_file, temp_file)
        fix_wav_file_in_place(temp_file)
        audio = pydub.AudioSegment.from_wav(temp_file)

        min_silence_len = 800
        silence_thresh = -50
        chunks = pydub.silence.split_on_silence(audio, 
            min_silence_len=min_silence_len,
            silence_thresh=silence_thresh,
            keep_silence=min_silence_len
        )

        chunks_size = self.chunks_size
        if len(chunks) <= chunks_size:
            return
        
        logger.info(f"时长:{len(audio)/1000}秒, 共:{len(chunks)} 段, 已处理{self.chunks_size},文件:{temp_file}")
        for i in range(chunks_size, len(chunks)):
            chunk = chunks[i]
            # 如果最后一段小于800ms,则表示话没说完,不保存分段
            if i == len(chunks) - 1:
                if len(chunk) < min_silence_len:
                    break
                # 获取最后800ms的音频段
                last_ms = chunk[-min_silence_len:]
                # 计算最后的RMS值(均方根，表示音量大小)
                rms = last_ms.rms
                # 将RMS值转换为dBFS (分贝全刻度)
                dbfs = 20 * math.log10(rms / 32768) if rms > 0 else -100
                # 如果低于-50 dBFS阈值，认为是静音
                if dbfs >= silence_thresh:
                    break

            chunk_file = f"{base_name}_{i}{ext}"
            chunk.export(chunk_file, format="wav")  
            logger.info(f"保存录音文件: {chunk_file}")
            self.chunks_size += 1
            self.file_list.append(chunk_file)
            self.whisper_manager.transcribe(chunk_file)

    def process_file_list(self):
        """处理对话列表"""
        process_talk = len(self.talk_list)
        if process_talk >= len(self.file_list):
            return
            
        for i in range(process_talk, len(self.file_list)):
            chunk_file = self.file_list[i]
            # 获取转录结果，如果可用
            if self.whisper_manager.is_transcription_complete(chunk_file):
                talk = ''
                try:
                    result = self.whisper_manager.get_result(chunk_file)
                    if result:
                        talk = result.get("text", "").strip()
                        # 如果成功识别到文本，调用回调
                        if talk and talk != '':
                            self.response_callback(talk)
                except Exception as e:
                    logger.error(f"获取异步转录结果失败: {e}")
                finally:
                    logger.info(f"获取到音频段 {i+1} 的转录结果: {talk[:30]}...")
                    self.talk_list.append(talk)

class SIPCaller:
    """SIP呼叫管理类"""
    def __init__(self, sip_config, tts_manager, whisper_manager):
        self.config = sip_config
        self.ep = None
        self.acc = None
        self.current_call = None
        self.phone_number = None
        self.whisper_manager = whisper_manager
        
        # 初始化ResponseManager
        self.response_manager = ResponseManager(yaml_file="response.yaml")
        
        # 初始化TTS管理器
        self.tts_manager = tts_manager
        
        # 初始化PJSIP
        self._init_pjsua2()
        
        # 预先生成所有可能回复的语音文件
        self._pregenerate_tts_responses()
        
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

    def _pregenerate_tts_responses(self):
        """预先生成所有可能回复的语音文件"""
        try:
            logger.info("开始预生成所有可能回复的语音文件...")
            
            # 获取所有可能的回复内容
            all_responses = self.response_manager.get_all_possible_responses()
            
            if not all_responses:
                logger.warning("未找到可能的回复内容，跳过预生成语音文件")
                return
                
            logger.info(f"找到 {len(all_responses)} 条可能的回复内容")
            
            # 计数器
            success_count = 0
            fail_count = 0
            cache_count = 0
            
            # 生成所有回复的语音文件
            for response_text in all_responses:
                try:
                    # 使用TTSManager生成语音
                    voice_file = self.tts_manager.generate_tts_sync(response_text)
                    
                    if voice_file:
                        if self.tts_manager.is_from_cache(response_text, voice_name):
                            logger.debug(f"使用缓存的TTS文件: {os.path.basename(voice_file)}")
                            cache_count += 1
                        else:
                            logger.debug(f"生成TTS文件成功: {os.path.basename(voice_file)}")
                            success_count += 1
                    else:
                        logger.warning(f"生成TTS文件失败: {response_text[:30]}...")
                        fail_count += 1
                except Exception as e:
                    logger.error(f"生成TTS文件时出错: {e}")
                    fail_count += 1
            
            logger.info(f"TTS预生成完成: 成功 {success_count} 个, 使用缓存 {cache_count} 个, 失败 {fail_count} 个")
            
        except Exception as e:
            logger.error(f"预生成TTS回复时出错: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
    


    def make_call(self, number):
        """拨打电话"""
        if self.current_call:
            logger.warning("已有通话在进行中")
            return None

        try:
            # 清理数据
            self.phone_number = number.strip()
            logger.info(f"=== 开始拨号 ===")
            logger.info(f"目标号码: {self.phone_number}")
            
            # 构建SIP URI
            sip_uri = f"sip:{self.phone_number}@{self.config.get('server', '')}:{self.config.get('port', '')}"
            logger.info(f"SIP URI: {sip_uri}")
            logger.info(f"SIP账户: {self.config.get('username', '')}@{self.config.get('server', '')}:{self.config.get('port', '')}")

            # 创建通话对象，并传入电话号码和响应语音文件
            call = SIPCall(self.acc, self.whisper_manager, number)
            # 传递tts_manager和response_manager到通话对象
            call.tts_manager = self.tts_manager
            call.response_manager = self.response_manager
            
            # 设置呼叫参数
            call_param = pj.CallOpParam(True)

            # 发送拨号请求
            logger.info(f"发送拨号请求: {sip_uri}")
            call.makeCall(sip_uri, call_param)
            
            # 更新当前通话
            self.current_call = call
            self.phone_number = number
            logger.info("拨号请求已发送,等待呼叫状态变化...")
            return call
        except Exception as e:
            logger.error(f"拨打电话失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None

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
