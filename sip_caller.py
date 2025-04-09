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

# 引入TTSManager
from tts_manager import TTSManager

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

    def _load_response_file(self):
        """加载响应语音文件"""
        try:
            # 检查文件扩展名
            if self.response_voice_file.lower().endswith('.mp3'):
                logger.info(f"检测到MP3响应文件: {self.response_voice_file}")
                # MP3文件需要转换为WAV格式
                self._convert_mp3_to_wav(self.response_voice_file)
                # 转换后的文件路径
                self.response_voice_file = self.response_voice_file.rsplit('.', 1)[0] + '.wav'
                
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
            # 创建recordings目录
            recordings_dir = "recordings"
            os.makedirs(recordings_dir, exist_ok=True)
            
            # 清理电话号码中的特殊字符，只保留数字
            clean_number = ''.join(filter(str.isdigit, phone_number))
            
            # 创建录音文件名，格式：电话号码_日期时间.wav
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{clean_number}_{timestamp}.wav"
            self.recording_file = os.path.join(recordings_dir, filename)
            
            # 创建录音器
            self.recorder = pj.AudioMediaRecorder()
            self.recorder.createRecorder(self.recording_file)
            
            # 连接到通话 - 恢复到之前的录音方式
            try:
                # 首先尝试使用getAudioMedia方法
                call_media = self.getAudioMedia(-1)  # -1表示第一个可用的音频媒体
                logger.info(f"成功获取音频媒体")
            except Exception as e:
                logger.error(f"无法获取音频媒体: {e}")
                logger.error("录音功能不可用")
                return False
                
            # 开始录音
            call_media.startTransmit(self.recorder)
            
            logger.info(f"开始录音: {self.recording_file}")
            return True
            
        except Exception as e:
            logger.error(f"录音启动失败: {e}")
            self.recording_file = None
            return False
    
    def stop_recording(self):
        """停止录音"""
        try:
            if self.recorder:
                # 停止录音
                self.recorder = None
                logger.info(f"录音已停止: {self.recording_file}")
                return True
            return False
        except Exception as e:
            logger.error(f"停止录音失败: {e}")
            return False
    
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
                    # 确保处理前没有其他程序占用文件
                    if os.path.exists(self.recording_file + ".temp"):
                        os.remove(self.recording_file + ".temp")
                    
                    # 复制一份文件进行处理，避免文件锁定问题
                    shutil.copy2(self.recording_file, self.recording_file + ".temp")
                    temp_file = self.recording_file + ".temp"
                    
                    # 使用更安全的方式调用whisper transcribe
                    try:
                        result = self.whisper_model.transcribe(
                            temp_file,
                            language="zh",
                            task="transcribe",
                            verbose=False
                        )
                        
                        # 清理临时文件
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                            
                        if isinstance(result, dict) and 'text' in result:
                            logger.info(f"语音识别结果: {result['text']}")
                            return result['text']
                        else:
                            logger.warning(f"语音识别结果格式异常: {type(result)}")
                            if isinstance(result, dict):
                                logger.warning(f"可用键: {result.keys()}")
                            return str(result) if result else None
                    except Exception as e:
                        logger.error(f"Whisper处理失败: {e}")
                        import traceback
                        logger.error(f"详细错误: {traceback.format_exc()}")
                        
                        # 尝试降级处理，直接使用模型处理音频文件
                        try:
                            import numpy as np
                            import soundfile as sf
                            
                            # 加载音频文件
                            logger.info(f"尝试使用降级方法处理录音文件: {temp_file}")
                            audio, sr = sf.read(temp_file)
                            
                            # 如果是双声道，转换为单声道
                            if len(audio.shape) > 1 and audio.shape[1] > 1:
                                audio = np.mean(audio, axis=1)
                            
                            # 如果采样率不是16kHz，进行重采样
                            if sr != 16000:
                                from scipy import signal
                                target_len = int(len(audio) * 16000 / sr)
                                audio = signal.resample(audio, target_len)
                                sr = 16000
                            
                            # 直接使用模型处理音频数据
                            result = self.whisper_model.transcribe(
                                audio,
                                sampling_rate=sr,
                                language="zh",
                                task="transcribe",
                                verbose=False
                            )
                            
                            if isinstance(result, dict) and 'text' in result:
                                logger.info(f"降级方法语音识别结果: {result['text']}")
                                return result['text']
                            else:
                                logger.warning(f"降级方法语音识别结果格式异常: {type(result)}")
                                return None
                        except Exception as e2:
                            logger.error(f"降级处理也失败: {e2}")
                            import traceback
                            logger.error(f"详细错误: {traceback.format_exc()}")
                            return None
                except Exception as e:
                    logger.error(f"语音识别处理失败: {e}")
                    import traceback
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    return None
            else:
                logger.warning(f"录音文件不存在: {self.recording_file}")
            return None
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
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
    
    def onCallMediaState(self, prm):
        """处理呼叫媒体状态改变事件"""
        try:
            ci = self.getInfo()
            logger.info(f"呼叫媒体状态改变，当前呼叫状态: {ci.stateText}")
            
            # 检查是否有音频媒体
            if self.getMedia(0):
                # 获取呼叫的音频媒体
                call_media = self.getMedia(0)
                
                # 检查音频方向
                if call_media.getDir() == pj.PJMEDIA_DIR_ENCODING_DECODING:
                    logger.info("音频媒体双向可用")
                elif call_media.getDir() == pj.PJMEDIA_DIR_ENCODING:
                    logger.info("音频媒体仅发送可用")
                elif call_media.getDir() == pj.PJMEDIA_DIR_DECODING:
                    logger.info("音频媒体仅接收可用")
                else:
                    logger.info(f"音频媒体方向: {call_media.getDir()}")
                
                # 获取呼叫的音频媒体
                try:
                    self.audio_media = self.getAudioMedia(-1)
                    
                    if not self.audio_media:
                        logger.error("无法获取音频媒体")
                        return
                    
                    # 创建录音设备
                    if not self.audio_recorder:
                        self.audio_recorder = pj.AudioMediaRecorder()
                        # 创建录音文件
                        if self.phone_number:
                            os.makedirs("recordings", exist_ok=True)
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            self.recording_file = f"recordings/call_{self.phone_number}_{timestamp}.wav"
                            
                            try:
                                logger.info(f"创建录音文件: {self.recording_file}")
                                self.audio_recorder.createRecorder(self.recording_file)
                                logger.info("录音设备创建成功")
                            except Exception as e:
                                logger.error(f"创建录音文件失败: {e}")
                                self.recording_file = None
                                self.audio_recorder = None
                                return
                    
                    # 连接音频媒体到录音设备
                    logger.info("连接音频媒体到录音设备")
                    self.audio_media.startTransmit(self.audio_recorder)
                    logger.info("开始录音")
                    
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
            else:
                logger.warning("没有可用的音频媒体")
                
        except Exception as e:
            logger.error(f"处理呼叫媒体状态改变时出错: {e}")
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
                
                # 检查是否需要播放响应（从主线程处理）
                def check_and_play_response():
                    # 在一个循环中检查should_play_response标记
                    check_count = 0
                    while check_count < 60:  # 最多检查60次，30秒
                        check_count += 1
                        time.sleep(0.5)
                        
                        if not hasattr(self, 'should_play_response') or not self.should_play_response:
                            continue
                            
                        # 如果标记被设置，则播放响应
                        try:
                            logger.info("检测到should_play_response标记，播放响应语音")
                            self.play_response_from_main_thread()
                            return  # 播放后退出循环
                        except Exception as e:
                            logger.error(f"从主线程播放响应失败: {e}")
                            import traceback
                            logger.error(f"详细错误: {traceback.format_exc()}")
                            return
                
                # 启动检查线程
                response_check_thread = threading.Thread(
                    target=check_and_play_response,
                    daemon=True
                )
                response_check_thread.start()
                
            elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                logger.info(f"通话已结束: 状态码={ci.lastStatusCode}, 原因={ci.lastReason}")
                
                # 停止音频传输
                try:
                    if hasattr(self, 'audio_media') and self.audio_media:
                        self.audio_media.stopTransmit(self.audio_recorder)
                except Exception as e:
                    logger.error(f"停止音频传输时出错: {e}")
                
                # 停止实时语音转录
                if hasattr(self, 'transcriber_thread') and self.transcriber_thread:
                    logger.info("实时语音转录已停止")
                    self.transcriber_active = False
                    self.transcriber_thread.join(timeout=2)
                
                # 停止录音
                if self.recorder:
                    self.stop_recording()
                    
                    # 转录通话录音
                    self.transcribe_audio()
                    
        except Exception as e:
            logger.error(f"处理呼叫状态变化时出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")

    def start_realtime_transcription_thread(self):
        """启动实时转录线程"""
        try:
            # 创建线程，但不立即启动，等待录音启动完成
            self.transcriber_active = True
            self.transcriber_thread = threading.Thread(
                target=self._realtime_transcription_loop,
                daemon=True
            )
            self.transcriber_thread.start()
            logger.info("实时转录线程已启动")
            return True
        except Exception as e:
            logger.error(f"启动实时转录线程失败: {e}")
            return False

    def _realtime_transcription_loop(self):
        """实时转录循环"""
        try:
            # 不再尝试注册线程到PJSIP，因为我们不会在这里直接使用PJSIP函数
            
            logger.info(f"开始实时转录循环，监控录音文件: {self.recording_file}")
            last_size = 0
            last_transcription_time = time.time()
            min_chunk_size = 8000  # 至少8KB新数据才处理
            segment_count = 0
            has_played_response = False
            
            # 等待录音文件创建
            while self.transcriber_active and not os.path.exists(self.recording_file):
                logger.info(f"等待录音文件创建: {self.recording_file}")
                time.sleep(0.5)
            
            if not os.path.exists(self.recording_file):
                logger.error(f"录音文件未创建: {self.recording_file}")
                return
                
            logger.info(f"录音文件已创建，开始监控: {self.recording_file}")
            
            # 主循环
            while self.transcriber_active:
                try:
                    # 检查文件是否存在
                    if not os.path.exists(self.recording_file):
                        logger.error(f"录音文件已消失: {self.recording_file}")
                        break
                        
                    # 获取当前文件大小
                    current_size = os.path.getsize(self.recording_file)
                    
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
                        try:
                            # 创建临时分段目录
                            segment_dir = "segments"
                            os.makedirs(segment_dir, exist_ok=True)
                            
                            segment_file = os.path.join(segment_dir, f"segment_{segment_count}.wav")
                            
                            # 复制整个录音文件
                            shutil.copy2(self.recording_file, segment_file)
                            
                            # 使用ffmpeg预处理音频，确保格式正确，这步很重要
                            processed_file = os.path.join(segment_dir, f"processed_{segment_count}.wav")
                            try:
                                # 使用ffmpeg规范化音频，确保它是有效的
                                import subprocess
                                cmd = [
                                    "ffmpeg", "-y", 
                                    "-i", segment_file, 
                                    "-ar", "16000",  # 采样率16kHz
                                    "-ac", "1",      # 单声道
                                    "-c:a", "pcm_s16le",  # 16位PCM
                                    processed_file
                                ]
                                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                                logger.info(f"音频预处理成功: {processed_file}")
                                
                                # 检查预处理文件
                                if os.path.exists(processed_file) and os.path.getsize(processed_file) > 1000:
                                    # 使用简单直接的方式转录
                                    text = None
                                    if self.whisper_model:
                                        try:
                                            # 直接调用Whisper API
                                            result = self.whisper_model.transcribe(
                                                processed_file,
                                                language="zh",
                                                fp16=False
                                            )
                                            text = result.get("text", "").strip()
                                            
                                            if text:
                                                logger.info(f"语音识别结果 (段{segment_count}): {text}")
                                                
                                                # 在第一次成功识别后播放响应语音
                                                if not has_played_response and self.response_voice_file and os.path.exists(self.response_voice_file):
                                                    logger.info(f"检测到语音，设置响应播放标记: {self.response_voice_file}")
                                                    # 设置标记，由主线程处理播放
                                                    self.should_play_response = True
                                                    has_played_response = True
                                            else:
                                                logger.info(f"语音识别结果为空 (段{segment_count})")
                                        except Exception as e:
                                            logger.error(f"转录过程中出错: {e}")
                                            import traceback
                                            logger.error(f"详细错误: {traceback.format_exc()}")
                                else:
                                    logger.warning(f"预处理后的音频文件过小或不存在: {processed_file}")
                            except Exception as e:
                                logger.error(f"音频预处理失败: {e}")
                                import traceback
                                logger.error(f"详细错误: {traceback.format_exc()}")
                            
                            # 更新上次处理的位置和时间
                            last_size = current_size
                            last_transcription_time = time.time()
                            
                            # 清理临时文件
                            try:
                                if os.path.exists(segment_file):
                                    os.remove(segment_file)
                                if os.path.exists(processed_file):
                                    os.remove(processed_file)
                            except Exception as e:
                                logger.warning(f"无法删除临时文件: {e}")
                            
                        except Exception as e:
                            logger.error(f"处理音频段 {segment_count} 时出错: {e}")
                            import traceback
                            logger.error(f"详细错误: {traceback.format_exc()}")
                    
                    # 短暂休眠
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"实时转录循环出错: {e}")
                    import traceback
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    time.sleep(1)
            
            logger.info("实时转录循环结束")
            
        except Exception as e:
            logger.error(f"实时转录线程出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
        
        self.transcriber_active = False

    def play_response_from_main_thread(self):
        """在主线程中播放响应语音"""
        if not self.response_voice_file or not os.path.exists(self.response_voice_file):
            logger.error(f"响应语音文件不存在: {self.response_voice_file}")
            return False
            
        try:
            logger.info(f"从主线程播放响应语音: {self.response_voice_file}")
            
            # 创建音频播放器
            player = pj.AudioMediaPlayer()
            player.createPlayer(self.response_voice_file)
            
            # 获取通话媒体
            audio_stream = self.getAudioMedia(-1)
            if not audio_stream:
                logger.error("无法获取音频媒体，无法播放响应语音")
                return False
                
            # 开始传输音频
            player.startTransmit(audio_stream)
            logger.info("响应语音播放已开始")
            self.has_played_response = True
            self.should_play_response = False
            return True
            
        except Exception as e:
            logger.error(f"从主线程播放响应语音失败: {e}")
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
        
        # 添加音频播放命令队列和处理线程
        self.play_commands = []
        self.play_commands_lock = threading.Lock()
        self.play_commands_thread_active = True
        self.play_commands_thread = threading.Thread(
            target=self._process_play_commands,
            daemon=True
        )
        self.play_commands_thread.start()
        
        # 初始化PJSIP
        self._init_pjsua2()

    # 添加音频播放命令处理函数
    def _play_audio_on_main_thread(self, command):
        """在主线程中处理音频播放命令"""
        with self.play_commands_lock:
            self.play_commands.append(command)

    def _process_play_commands(self):
        """处理音频播放命令队列的线程"""
        try:
            # 注册线程到PJSIP
            try:
                import ctypes
                # 创建一个Thread描述结构
                thread_desc = pj.PJ_THREAD_DESC()
                thread_desc.desc = ctypes.c_char_p(b"PlayCommandProcessor")
                # 创建一个线程槽
                thread_this = pj.PJ_THREAD_THIS()
                # 注册线程
                pj.thread_register("PlayCommandProcessor", thread_desc, thread_this)
                logger.info("已将音频播放命令处理线程注册到PJSIP")
            except Exception as e:
                logger.error(f"注册音频处理线程到PJSIP失败: {e}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
                return

            while self.play_commands_thread_active:
                commands_to_process = []
                
                # 获取要处理的命令
                with self.play_commands_lock:
                    if self.play_commands:
                        commands_to_process = self.play_commands.copy()
                        self.play_commands.clear()
                
                # 处理命令
                for cmd in commands_to_process:
                    try:
                        # 创建音频播放器
                        player = pj.AudioMediaPlayer()
                        player.createPlayer(cmd.file_path)
                        
                        # 获取通话媒体
                        call = cmd.call
                        audio_stream = call.getAudioMedia(-1)
                        
                        if audio_stream:
                            # 开始传输音频
                            player.startTransmit(audio_stream)
                            cmd.success = True
                            logger.info(f"在主线程成功播放音频: {cmd.file_path}")
                        else:
                            cmd.success = False
                            cmd.error = "无法获取音频媒体"
                            logger.error("无法获取音频媒体，无法播放响应")
                    except Exception as e:
                        cmd.success = False
                        cmd.error = str(e)
                        logger.error(f"主线程播放音频失败: {e}")
                        import traceback
                        logger.error(f"详细错误: {traceback.format_exc()}")
                    finally:
                        # 标记命令已完成
                        cmd.done.set()
                
                # 短暂休眠
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"音频播放命令处理线程出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
        
        logger.info("音频播放命令处理线程已退出")

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
            
            # 设置日志级别
            ep_cfg.logConfig.level = 5  # 设置为高级别日志，便于调试
            ep_cfg.logConfig.consoleLevel = 5
            
            # 初始化媒体配置
            ep_cfg.medConfig.ecTailLen = 0  # 禁用回声消除
            
            # 初始化PJSIP库
            logger.info("正在初始化PJSIP库...")
            self.ep.libInit(ep_cfg)
            logger.info("PJSIP库初始化成功")

            # 创建传输
            sipTpConfig = pj.TransportConfig()
            if self.config.get('bind_port'):
                sipTpConfig.port = self.config.get('bind_port', 5060)
            else:
                sipTpConfig.port = random.randint(6000, 8000)
            
            # 指定本地IP（如果配置中有）
            if self.config.get('bind_ip'):
                sipTpConfig.boundAddr = self.config.get('bind_ip')
                logger.info(f"绑定本地IP: {sipTpConfig.boundAddr}:{sipTpConfig.port}")
            
            logger.info(f"创建SIP传输，端口: {sipTpConfig.port}")
            self.transport_id = self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, sipTpConfig)
            logger.info(f"SIP传输创建成功，ID: {self.transport_id}")
            # transportCreate返回的是整数ID，不是对象，无法直接调用getInfo()
            # 记录一下基本信息即可
            logger.info(f"本地SIP端口: {sipTpConfig.port}")

            # 启动库
            logger.info("启动PJSIP库...")
            self.ep.libStart()
            logger.info("PJSIP库启动成功")

            # 创建账户配置
            acc_cfg = pj.AccountConfig()
            # 使用安全的get方法获取配置值，避免KeyError
            username = self.config.get('username', '')
            server = self.config.get('server', '')
            port = self.config.get('port', '')
            
            acc_cfg.idUri = f"sip:{username}@{server}:{port}"
            acc_cfg.regConfig.registrarUri = f"sip:{server}:{port}"
            
            # 配置认证信息
            cred_info = pj.AuthCredInfo(
                "digest",
                "*",
                username,
                0,
                self.config.get('password', '')
            )
            acc_cfg.sipConfig.authCreds.append(cred_info)
            
            # 设置注册超时时间
            if self.config.get('register_refresh'):
                acc_cfg.regConfig.timeoutSec = int(self.config.get('register_refresh'))
                logger.info(f"设置注册刷新时间: {acc_cfg.regConfig.timeoutSec}秒")
            
            # 设置Keep-Alive时间 - 注释掉这部分，因为在Python绑定中不存在这个属性
            # if self.config.get('keep_alive'):
            #     acc_cfg.sipConfig.keepAliveIntervalSec = int(self.config.get('keep_alive'))
            #     logger.info(f"设置Keep-Alive时间: {acc_cfg.sipConfig.keepAliveIntervalSec}秒")
            
            logger.info(f"创建SIP账户: {acc_cfg.idUri}, 注册到: {acc_cfg.regConfig.registrarUri}")

            # 创建账户
            self.acc = pj.Account()
            self.acc.create(acc_cfg)
            
            # 等待注册完成
            logger.info("等待SIP注册...")
            timeout = 30  # 30秒超时
            start_time = time.time()
            
            # 修复部分：确保self.acc是有效的Account对象，并且可以调用getInfo()
            # 同时处理可能的异常情况
            while time.time() - start_time < timeout:
                try:
                    if not isinstance(self.acc, pj.Account):
                        logger.error(f"账户对象类型错误: {type(self.acc)}")
                        break
                        
                    acc_info = self.acc.getInfo()
                    if acc_info.regStatus == pj.PJSIP_SC_OK:
                        logger.info("SIP注册成功")
                        break
                    elif acc_info.regStatus >= 300:  # 任何错误状态码
                        logger.error(f"SIP注册失败，状态码: {acc_info.regStatus}")
                        break
                except Exception as e:
                    logger.error(f"获取账户信息时出错: {e}")
                    break
                    
                time.sleep(0.5)  # 稍微增加检查间隔，减少CPU使用
            
            # 再次检查注册状态
            try:
                if isinstance(self.acc, pj.Account):
                    acc_info = self.acc.getInfo()
                    logger.info(f"SIP账户信息: URI={acc_info.uri}, 状态码={acc_info.regStatus}, 过期={acc_info.regExpiresSec}秒")
                    
                    if acc_info.regStatus != pj.PJSIP_SC_OK:
                        logger.warning(f"SIP注册未成功完成，状态码: {acc_info.regStatus}")
                else:
                    logger.error("账户对象无效")
            except Exception as e:
                logger.error(f"获取最终账户状态时出错: {e}")

            logger.info("SIP客户端初始化成功")
        except pj.Error as e:
            logger.error(f"初始化PJSIP失败: {e}")
            if hasattr(e, 'info'):
                logger.error(f"详细错误信息: {e.info()}")
            raise
        except Exception as e:
            logger.error(f"初始化PJSIP过程中出现非PJSIP错误: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            raise

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
            
            # 设置播放命令回调函数
            call.play_command_callback = self._play_audio_on_main_thread
            
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
            # 停止播放命令处理线程
            self.play_commands_thread_active = False
            if hasattr(self, 'play_commands_thread') and self.play_commands_thread:
                self.play_commands_thread.join(timeout=2)
            
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