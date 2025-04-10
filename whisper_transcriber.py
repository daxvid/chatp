import os
import time
import logging
import shutil
import threading
import subprocess
import traceback

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

logger = logging.getLogger("sip")

class WhisperTranscriber:
    """Whisper语音转文本处理类"""
    
    def __init__(self, whisper_model=None):
        self.whisper_model = whisper_model
        self.transcriber_active = False
        self.transcriber_thread = None
        self.recording_file = None
        self.response_callback = None
        self.play_response_callback = None
    
    def set_model(self, model):
        """设置Whisper模型"""
        self.whisper_model = model
    
    def transcribe_file(self, audio_file):
        """转录单个音频文件"""
        try:
            if not self.whisper_model:
                logger.error("Whisper模型未加载，无法进行语音识别")
                return None
                
            if audio_file and os.path.exists(audio_file):
                logger.info(f"开始转录音频: {audio_file}")
                # 检查文件大小，确保不是空文件
                if os.path.getsize(audio_file) < 1000:  # 小于1KB的文件可能有问题
                    logger.warning(f"录音文件过小，可能没有录到声音: {audio_file}")
                    return None
                
                try:
                    # 确保处理前没有其他程序占用文件
                    temp_file = audio_file + ".temp"
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                    
                    # 复制一份文件进行处理，避免文件锁定问题
                    shutil.copy2(audio_file, temp_file)
                    
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
                        logger.error(f"详细错误: {traceback.format_exc()}")
                        
                        # 尝试降级处理
                        if HAVE_SOUNDFILE and HAVE_NUMPY:
                            try:
                                # 加载音频文件
                                logger.info(f"尝试使用降级方法处理录音文件: {temp_file}")
                                audio, sr = sf.read(temp_file)
                                
                                # 如果是双声道，转换为单声道
                                if len(audio.shape) > 1 and audio.shape[1] > 1:
                                    audio = np.mean(audio, axis=1)
                                
                                # 如果采样率不是16kHz，进行重采样
                                if sr != 16000 and HAVE_SCIPY:
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
                                logger.error(f"详细错误: {traceback.format_exc()}")
                                return None
                        else:
                            logger.error("无法使用降级处理，缺少必要的库")
                            return None
                except Exception as e:
                    logger.error(f"语音识别处理失败: {e}")
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    return None
            else:
                logger.warning(f"录音文件不存在: {audio_file}")
            return None
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
    
    def start_realtime_transcription(self, recording_file, response_callback=None, play_response_callback=None):
        """启动实时转录线程
        
        Args:
            recording_file (str): 录音文件路径
            response_callback (callable): 转录结果回调函数
            play_response_callback (callable): 播放响应回调函数
        """
        try:
            self.recording_file = recording_file
            self.response_callback = response_callback
            self.play_response_callback = play_response_callback
            
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
    
    def stop_transcription(self):
        """停止实时转录"""
        if self.transcriber_active:
            self.transcriber_active = False
            if self.transcriber_thread:
                self.transcriber_thread.join(timeout=2)
                self.transcriber_thread = None
            logger.info("实时语音转录已停止")
    
    def _realtime_transcription_loop(self):
        """实时转录循环"""
        try:
            logger.info(f"开始实时转录循环，监控录音文件: {self.recording_file}")
            last_size = 0
            last_transcription_time = time.time()
            min_chunk_size = 8000  # 至少8KB新数据才处理
            segment_count = 0
            has_played_response = False
            max_retries = 3  # 添加重试次数
            
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
                                    # 转录处理
                                    text = self._transcribe_segment(processed_file, segment_count)
                                    
                                    # 如果成功识别到文本，调用回调
                                    if text and not has_played_response:
                                        logger.info(f"检测到语音，准备响应")
                                        
                                        # 如果提供了转录结果回调函数，调用它
                                        if self.response_callback:
                                            self.response_callback(text)
                                        
                                        # 如果提供了播放响应回调函数，调用它
                                        if self.play_response_callback:
                                            self.play_response_callback()
                                            has_played_response = True
                                else:
                                    logger.warning(f"预处理后的音频文件过小或不存在: {processed_file}")
                            except Exception as e:
                                logger.error(f"音频预处理失败: {e}")
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
                            logger.error(f"详细错误: {traceback.format_exc()}")
                    
                    # 短暂休眠
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"实时转录循环出错: {e}")
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    time.sleep(1)
            
            logger.info("实时转录循环结束")
            
        except Exception as e:
            logger.error(f"实时转录线程出错: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
        
        self.transcriber_active = False
    
    def _transcribe_segment(self, processed_file, segment_count):
        """转录单个音频段，含重试逻辑"""
        if not self.whisper_model:
            logger.warning("Whisper模型未加载，无法进行语音识别")
            return None
            
        max_retries = 3
        retry_count = 0
        segment_dir = os.path.dirname(processed_file)
        
        while retry_count < max_retries:
            try:
                # 使用原始方法直接转录文件
                logger.info(f"尝试转录音频段 {segment_count} (尝试 {retry_count+1}/{max_retries})")
                result = self.whisper_model.transcribe(
                    processed_file,
                    language="zh",
                    fp16=False
                )
                text = result.get("text", "").strip()
                
                if text:
                    logger.info(f"语音识别结果 (段{segment_count}): {text}")
                    return text
                else:
                    logger.info(f"语音识别结果为空 (段{segment_count})")
                    
                # 成功则跳出重试循环
                break
                
            except Exception as e:
                retry_count += 1
                logger.error(f"转录尝试 {retry_count}/{max_retries} 失败: {e}")
                logger.error(f"详细错误: {traceback.format_exc()}")
                
                # 尝试使用复制的文件
                if retry_count < max_retries:
                    try:
                        # 重新复制一个文件尝试
                        retry_file = os.path.join(segment_dir, f"retry_{segment_count}_{retry_count}.wav")
                        shutil.copy2(processed_file, retry_file)
                        logger.info(f"尝试使用新复制的文件: {retry_file}")
                        
                        result = self.whisper_model.transcribe(
                            retry_file,
                            language="zh",
                            fp16=False
                        )
                        text = result.get("text", "").strip()
                        
                        if text:
                            logger.info(f"语音识别结果 (段{segment_count}-重试): {text}")
                            
                            # 清理临时文件
                            try:
                                os.remove(retry_file)
                            except:
                                pass
                                
                            # 成功返回结果
                            return text
                    except Exception as er:
                        logger.error(f"重试文件处理失败: {er}")
                
                if retry_count >= max_retries:
                    logger.error(f"转录段 {segment_count} 失败，已达最大尝试次数")
                    # 尝试使用替代方法
                    try:
                        logger.info(f"尝试使用替代方法转录...")
                        
                        # 尝试使用系统命令转录（如果安装了whisper命令行工具）
                        try:
                            cmd = [
                                "whisper", processed_file,
                                "--language", "zh",
                                "--model", "small",
                                "--output_format", "txt",
                                "--output_dir", segment_dir
                            ]
                            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                            output_file = os.path.join(segment_dir, f"processed_{segment_count}.txt")
                            
                            if os.path.exists(output_file):
                                with open(output_file, 'r', encoding='utf-8') as f:
                                    text = f.read().strip()
                                    if text:
                                        logger.info(f"替代方法语音识别结果 (段{segment_count}): {text}")
                                        return text
                        except Exception as e3:
                            logger.error(f"替代转录方法也失败: {e3}")
                    except Exception as e2:
                        logger.error(f"尝试替代方法失败: {e2}")
                
                # 等待一会再重试
                time.sleep(1)
        
        return None 