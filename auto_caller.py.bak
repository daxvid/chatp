import pjsua2 as pj
import whisper
import edge_tts
import asyncio
import os
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from pathlib import Path
import logging
import time
import wave
import threading
from datetime import datetime
import ssl
import struct  # Add struct import for binary data handling

# 禁用全局SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Config:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
    @property
    def sip_config(self):
        return self.config['sip']
    
    @property
    def call_config(self):
        return self.config['call']
    
    @property
    def responses(self):
        return self.config['responses']

def load_whisper_model():
    # Create models directory if it doesn't exist
    model_dir = Path("models/whisper")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    # Set model path
    model_path = model_dir / "small.pt"
    
    # Load model from local path if exists, otherwise download
    try:
        model = whisper.load_model("small", download_root=str(model_dir))
        print(f"Loaded whisper model from {model_path}")
    except Exception as e:
        print(f"Error loading model from {model_path}: {e}")
        # 尝试禁用 SSL 验证后加载
        try:
            print("尝试禁用SSL验证后加载模型...")
            model = whisper.load_model("small", download_root=str(model_dir))
            print("Model downloaded successfully")
        except Exception as e2:
            print(f"仍然无法加载模型: {e2}")
            # 提供一个备用方案
            raise RuntimeError("无法加载语音识别模型，请确保网络连接或手动下载模型文件")
    
    return model

class MyCall(pj.Call):
    def __init__(self, acc, voice_file=None, whisper_model=None):
        pj.Call.__init__(self, acc)
        self.voice_file = voice_file
        self.voice_data = None
        self.voice_position = 0
        self.recorder = None
        self.recording_file = None
        self.whisper_model = whisper_model
        
        # 如果没有传入模型且需要，尝试加载
        if self.whisper_model is None:
            # 尝试加载 whisper 模型，带错误处理
            try:
                logger.info("尝试加载 Whisper 模型...")
                self.whisper_model = whisper.load_model("small")
                logger.info("Whisper 模型加载成功")
            except Exception as e:
                logger.error(f"Whisper 模型加载失败: {e}")
                self.whisper_model = None
            
        if self.voice_file:
            self._load_voice_file()

    def _load_voice_file(self):
        """加载语音文件"""
        try:
            # 检查文件扩展名
            if self.voice_file.lower().endswith('.mp3'):
                logger.info(f"检测到MP3文件: {self.voice_file}")
                # MP3文件需要转换为WAV格式
                self._convert_mp3_to_wav()
                # 转换后的文件路径
                self.voice_file = self.voice_file.rsplit('.', 1)[0] + '.wav'
                
            with wave.open(self.voice_file, 'rb') as wf:
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 8000:
                    logger.warning("语音文件不是单声道、16位、8kHz采样率，尝试转换...")
                    self._convert_to_compatible_wav()
                self.voice_data = wf.readframes(wf.getnframes())
                logger.info(f"语音文件加载成功: {self.voice_file}")
        except Exception as e:
            logger.error(f"加载语音文件失败: {e}")
            self.voice_data = None
            
    def _convert_mp3_to_wav(self):
        """将MP3文件转换为WAV格式"""
        try:
            import subprocess
            output_wav = self.voice_file.rsplit('.', 1)[0] + '.wav'
            
            # 使用ffmpeg转换
            cmd = [
                'ffmpeg', '-y', 
                '-i', self.voice_file, 
                '-acodec', 'pcm_s16le', 
                '-ar', '8000', 
                '-ac', '1', 
                output_wav
            ]
            
            logger.info(f"转换MP3到WAV: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            logger.info(f"MP3成功转换为WAV: {output_wav}")
            
        except Exception as e:
            logger.error(f"MP3转换失败: {e}")
            raise
            
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

    def start_recording(self, phone_number):
        """开始录音"""
        try:
            # 创建录音文件名：电话号码+时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.recording_file = f"recordings/{phone_number}_{timestamp}.wav"
            
            # 确保录音目录存在
            os.makedirs("recordings", exist_ok=True)
            
            # 创建录音器
            self.recorder = pj.AudioMediaRecorder()
            self.recorder.createRecorder(self.recording_file)
            
            # 开始录音
            self.getAudioVideoStream()[0].startTransmit(self.recorder)
            logger.info(f"开始录音: {self.recording_file}")
        except pj.Error as e:
            logger.error(f"开始录音失败: {e}")

    def stop_recording(self):
        """停止录音"""
        try:
            if self.recorder:
                self.getAudioVideoStream()[0].stopTransmit(self.recorder)
                self.recorder = None
                logger.info("停止录音")
        except pj.Error as e:
            logger.error(f"停止录音失败: {e}")

    def transcribe_audio(self):
        """使用Whisper转录音频"""
        try:
            if not self.whisper_model:
                logger.error("Whisper模型未加载，无法进行语音识别")
                return None
                
            if self.recording_file and os.path.exists(self.recording_file):
                logger.info(f"开始转录音频: {self.recording_file}")
                # 检查文件大小，确保不是空文件
                if os.path.getsize(self.recording_file) < 1000:  # 小于1KB的文件可能有问题
                    logger.warning(f"录音文件过小，可能没有录到声音: {self.recording_file}")
                
                try:
                    result = self.whisper_model.transcribe(self.recording_file)
                    logger.info(f"语音识别结果: {result['text']}")
                    return result['text']
                except Exception as e:
                    logger.error(f"语音识别处理失败: {e}")
                    return None
            else:
                logger.warning(f"录音文件不存在: {self.recording_file}")
            return None
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            return None

    def onCallState(self, prm):
        """处理通话状态变化"""
        ci = self.getInfo()
        logger.info(f"通话状态: {ci.stateText}")
        
        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            logger.info("通话已接通")
            if self.voice_data:
                # 创建音频播放器
                player = pj.AudioMediaPlayer()
                try:
                    player.createPlayer(self.voice_file)
                    # 连接到通话
                    player.startTransmit(self.getAudioVideoStream()[0])
                    
                    # 开始录音
                    self.start_recording(prm.remoteUri)
                except pj.Error as e:
                    logger.error(f"播放语音失败: {e}")
        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            logger.info("通话已结束")
            # 停止录音
            self.stop_recording()
            # 转录音频
            if self.recording_file:
                self.transcribe_audio()

    def start_realtime_transcription(self):
        """开始实时转录"""
        try:
            # 创建转录目录
            os.makedirs("transcriptions", exist_ok=True)
            
            # 清理之前的临时文件
            temp_files = [f for f in os.listdir() if f.startswith("temp_") and f.endswith(".wav")]
            for temp_file in temp_files:
                try:
                    os.remove(temp_file)
                    logger.debug(f"删除临时文件: {temp_file}")
                except Exception as e:
                    logger.warning(f"无法删除临时文件 {temp_file}: {e}")
            
            # 检查是否有有效的音频媒体
            try:
                if not self.getAudioVideoStream() or len(self.getAudioVideoStream()) == 0:
                    logger.error("无法获取通话音频流，无法开始实时转录")
                    return False
                
                audio_media = self.getAudioVideoStream()[0]
                if not audio_media:
                    logger.error("无法获取音频媒体，无法开始实时转录")
                    return False
                    
                logger.info("开始实时转录...")
                
                # 创建并启动转录线程
                self.transcription_running = True
                self.transcription_thread = threading.Thread(
                    target=self._transcription_loop,
                    args=(audio_media,)
                )
                self.transcription_thread.daemon = True
                self.transcription_thread.start()
                
                logger.info("实时转录已启动")
                return True
                
            except Exception as e:
                logger.error(f"获取音频流失败: {e}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
                return False
                
        except Exception as e:
            logger.error(f"启动实时转录失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False
            
    def _transcription_loop(self, audio_media):
        """实时转录循环处理"""
        try:
            # 定义音频参数
            SAMPLE_RATE = 16000  # Hz
            CHUNK_SIZE = 1600  # 每100ms的样本
            BUFFER_SECONDS = 5  # 缓冲区大小（秒）
            TRANSCRIBE_INTERVAL = 2  # 转录间隔（秒）
            
            # 初始化音频缓冲区
            audio_buffer = []
            last_transcribe_time = time.time()
            buffer_max_size = BUFFER_SECONDS * SAMPLE_RATE
            
            # 临时WAV文件计数
            temp_file_count = 0
            
            logger.info(f"转录参数: 采样率={SAMPLE_RATE}Hz, 块大小={CHUNK_SIZE}, 缓冲区={BUFFER_SECONDS}秒")
            
            # 注册媒体端口以接收音频数据
            port = pj.AudioMediaPort()
            audio_media.startTransmit(port)
            
            # 转录循环
            while self.transcription_running:
                try:
                    # 获取音频帧
                    frame = port.getFrame()
                    if frame:
                        # 将PCM数据转换为numpy数组
                        pcm_data = frame.buf
                        samples = np.frombuffer(pcm_data, dtype=np.int16)
                        
                        # 添加到缓冲区
                        audio_buffer.extend(samples)
                        
                        # 保持缓冲区大小
                        if len(audio_buffer) > buffer_max_size:
                            audio_buffer = audio_buffer[-buffer_max_size:]
                        
                        # 检查是否应该进行转录
                        current_time = time.time()
                        if current_time - last_transcribe_time >= TRANSCRIBE_INTERVAL and len(audio_buffer) > CHUNK_SIZE:
                            # 创建临时WAV文件
                            temp_file_name = f"temp_transcription_{temp_file_count}.wav"
                            temp_file_count += 1
                            
                            # 将缓冲区数据写入WAV文件
                            with wave.open(temp_file_name, 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)  # 2 bytes = 16 bits
                                wf.setframerate(SAMPLE_RATE)
                                audio_data = np.array(audio_buffer, dtype=np.int16).tobytes()
                                wf.writeframes(audio_data)
                            
                            # 使用Whisper转录
                            try:
                                result = self.whisper_model.transcribe(
                                    temp_file_name,
                                    language="zh",
                                    fp16=False
                                )
                                
                                transcription = result["text"].strip()
                                if transcription:
                                    logger.info(f"实时转录结果: {transcription}")
                                    
                                    # 保存转录结果到文件
                                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                                    transcription_file = f"transcriptions/transcription_{timestamp}.txt"
                                    with open(transcription_file, 'w', encoding='utf-8') as f:
                                        f.write(transcription)
                                        
                                    logger.debug(f"转录结果已保存到: {transcription_file}")
                            except Exception as e:
                                logger.error(f"转录过程中出错: {e}")
                                
                            # 尝试删除临时文件
                            try:
                                os.remove(temp_file_name)
                            except Exception as e:
                                logger.warning(f"无法删除临时文件 {temp_file_name}: {e}")
                                
                            last_transcribe_time = current_time
                    
                    # 小睡以减少CPU使用
                    time.sleep(0.01)
                    
                except Exception as e:
                    logger.error(f"转录循环中出错: {e}")
                    time.sleep(0.5)  # 出错后稍微暂停
            
            # 清理
            audio_media.stopTransmit(port)
            logger.info("转录循环已停止")
            
        except Exception as e:
            logger.error(f"转录线程出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            
    def stop_realtime_transcription(self):
        """停止实时转录"""
        if hasattr(self, 'transcription_running'):
            self.transcription_running = False
            if hasattr(self, 'transcription_thread') and self.transcription_thread:
                self.transcription_thread.join(timeout=2.0)
                logger.info("实时转录已停止")

class AutoCaller:
    def __init__(self, config_path='config.yaml'):
        self.config = self._load_config(config_path)
        self.ep = None
        self.acc = None
        self.current_call = None
        self.whisper_model = None
        self.tts_cache_dir = "tts_cache"
        
        # 创建TTS缓存目录
        os.makedirs(self.tts_cache_dir, exist_ok=True)
        
        # 预先加载 Whisper 模型
        try:
            logger.info("正在加载 Whisper 语音识别模型...")
            self.whisper_model = whisper.load_model("small")
            logger.info("Whisper 模型加载成功")
        except Exception as e:
            logger.error(f"无法加载 Whisper 模型: {e}")
            logger.warning("语音识别功能将不可用，但拨号功能可以正常使用")
        
        # 初始化PJSIP
        self._init_pjsua2()

    def _load_config(self, config_path):
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

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
            sipTpConfig.port = self.config['sip'].get('bind_port', 5060)
            self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, sipTpConfig)

            # 启动库
            self.ep.libStart()

            # 创建账户配置
            acc_cfg = pj.AccountConfig()
            acc_cfg.idUri = f"sip:{self.config['sip']['username']}@{self.config['sip']['server']}:{self.config['sip']['port']}"
            acc_cfg.regConfig.registrarUri = f"sip:{self.config['sip']['server']}:{self.config['sip']['port']}"
            acc_cfg.sipConfig.authCreds.append(
                pj.AuthCredInfo(
                    "digest",
                    "*",
                    self.config['sip']['username'],
                    0,
                    self.config['sip']['password']
                )
            )

            # 创建账户
            self.acc = pj.Account()
            self.acc.create(acc_cfg)

            # 等待注册完成
            while self.acc.getInfo().regStatus != pj.PJSIP_SC_OK:
                time.sleep(0.1)

            logger.info("SIP客户端初始化成功")
        except pj.Error as e:
            logger.error(f"初始化PJSIP失败: {e}")
            raise

    def make_call(self, number: str, voice_file: str = None):
        """拨打电话并播放语音"""
        try:
            if self.current_call:
                logger.warning("已有通话在进行中")
                return False

            # 清理号码中可能的特殊字符
            clean_number = ''.join(c for c in number if c.isdigit() or c in ['+', '*', '#'])
            
            # 构建SIP URI
            sip_uri = f"sip:{clean_number}@{self.config['sip']['server']}:{self.config['sip']['port']}"
            logger.info(f"正在拨打: {sip_uri}")
            
            # 添加更多调试信息
            logger.info(f"服务器信息: {self.config['sip']['server']}:{self.config['sip']['port']}")
            logger.info(f"账户信息: {self.config['sip']['username']}")
            
            # 打印当前网络连接信息
            try:
                import socket
                host_ip = socket.gethostbyname(socket.gethostname())
                logger.info(f"本机IP: {host_ip}")
            except Exception as e:
                logger.warning(f"获取本机IP失败: {e}")

            # 创建通话
            call = MyCall(self.acc, voice_file, self.whisper_model)
            call_prm = pj.CallOpParam()
            logger.info("开始拨号...")
            call.makeCall(sip_uri, call_prm)
            
            self.current_call = call
            logger.info("呼叫已建立")
            return True
                
        except pj.Error as e:
            logger.error(f"拨打电话失败: {e}")
            # 输出详细错误信息
            if hasattr(e, 'status') and hasattr(e, 'reason'):
                logger.error(f"SIP错误状态: {e.status}, 原因: {e.reason}")
            return False
        except Exception as e:
            logger.error(f"拨号过程中发生未知错误: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
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

    async def generate_tts(self, text, voice="zh-CN-XiaoxiaoNeural"):
        """使用edge-tts生成语音文件"""
        try:
            # 创建文件名（使用文本的哈希值）
            import hashlib
            text_hash = hashlib.md5(text.encode()).hexdigest()
            mp3_path = os.path.join(self.tts_cache_dir, f"{text_hash}_{voice}.mp3")
            wav_path = os.path.join(self.tts_cache_dir, f"{text_hash}_{voice}.wav")
            
            # 如果已经生成过，直接返回
            if os.path.exists(wav_path):
                logger.info(f"使用缓存的TTS文件: {wav_path}")
                return wav_path
                
            # 生成语音
            logger.info(f"正在使用edge-tts生成语音: '{text}'")
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(mp3_path)
            logger.info(f"TTS生成成功: {mp3_path}")
            
            # 转换为WAV格式
            self._convert_mp3_to_wav_file(mp3_path, wav_path)
            
            return wav_path
        except Exception as e:
            logger.error(f"TTS生成失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
            
    def _convert_mp3_to_wav_file(self, mp3_file, wav_file):
        """将MP3文件转换为PJSIP兼容的WAV格式"""
        try:
            import subprocess
            
            # 使用ffmpeg转换
            cmd = [
                'ffmpeg', '-y', 
                '-i', mp3_file, 
                '-acodec', 'pcm_s16le', 
                '-ar', '8000', 
                '-ac', '1', 
                wav_file
            ]
            
            logger.info(f"转换MP3到WAV: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            logger.info(f"MP3成功转换为WAV: {wav_file}")
            
        except Exception as e:
            logger.error(f"MP3转换失败: {e}")
            raise
    
    def make_call_with_text(self, number: str, text: str, voice="zh-CN-XiaoxiaoNeural"):
        """使用文本生成语音并拨打电话"""
        # 使用同步函数运行异步TTS生成
        try:
            # 运行异步函数
            wav_file = asyncio.run(self.generate_tts(text, voice))
            if not wav_file:
                logger.error("TTS生成失败，无法拨打电话")
                return False
                
            # 拨打电话并播放生成的语音
            return self.make_call(number, wav_file)
        except Exception as e:
            logger.error(f"使用TTS拨打电话失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False

def main():
    caller = None
    try:
        logger.info("正在启动自动拨号系统...")
        
        # 创建自动拨号器实例
        caller = AutoCaller()
        
        # 从配置文件获取目标号码和语音相关配置
        target_number = caller.config['sip'].get('target_number')
        tts_text = caller.config['sip'].get('tts_text')
        tts_voice = caller.config['sip'].get('tts_voice', 'zh-CN-XiaoxiaoNeural')
        voice_file = caller.config['sip'].get('voice_file')
        
        if not target_number:
            logger.error("配置文件中未指定目标号码")
            return
        
        logger.info(f"配置加载成功，准备拨打电话到: {target_number}")
        
        # 优先使用TTS文本，如果没有则使用预设的语音文件
        if tts_text:
            logger.info(f"使用TTS生成语音: '{tts_text}'")
            result = caller.make_call_with_text(target_number, tts_text, tts_voice)
        elif voice_file:
            # 检查文件是否存在
            if not os.path.exists(voice_file):
                logger.error(f"语音文件不存在: {voice_file}")
                return
                
            file_ext = os.path.splitext(voice_file)[1].lower()
            if file_ext == '.mp3':
                logger.info(f"将播放MP3文件: {voice_file}")
            elif file_ext == '.wav':
                logger.info(f"将播放WAV文件: {voice_file}")
            else:
                logger.error(f"不支持的音频格式: {file_ext}，支持的格式：.mp3, .wav")
                return
                
            result = caller.make_call(target_number, voice_file)
        else:
            logger.error("配置文件中既没有指定TTS文本也没有指定语音文件")
            return
        
        # 等待通话结束
        if result:
            logger.info("拨号成功，等待通话结束...")
            while caller.current_call:
                time.sleep(1)
            logger.info("通话已结束")
        else:
            logger.error("拨号失败")
        
    except pj.Error as e:
        logger.error(f"PJSUA2错误: {e}")
        # 输出详细的错误信息
        if hasattr(e, 'status') and hasattr(e, 'reason'):
            logger.error(f"SIP错误状态: {e.status}, 原因: {e.reason}")
        
    except ssl.SSLError as e:
        logger.error(f"SSL证书验证错误: {e}")
        logger.info("请尝试在系统级别禁用SSL证书验证，或者修改SSL证书配置")
        
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        
    finally:
        # 确保服务被正确停止
        logger.info("正在清理资源...")
        if caller:
            caller.stop()
        logger.info("程序结束")

if __name__ == "__main__":
    main() 