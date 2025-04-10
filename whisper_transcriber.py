import os
import time
import logging
import shutil
import threading
import subprocess
import traceback
import queue  # 添加queue模块导入，用于线程安全队列

# 引入AudioUtils类
from audio_utils import AudioUtils

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
        
        # 添加线程安全的识别结果队列
        self.transcription_queue = queue.Queue()
        # 是否已经通知过有新识别结果
        self.notified_new_transcription = False
    
    def set_model(self, model):
        """设置Whisper模型"""
        self.whisper_model = model
    
    def transcribe_file(self, audio_file):
        """转录单个音频文件"""
        try:
            if not self.whisper_model:
                logger.warning("Whisper模型未加载，无法进行语音识别")
                return None
                
            if audio_file and os.path.exists(audio_file):
                logger.info(f"开始转录音频: {audio_file}")
                # 检查文件大小，确保不是空文件
                if os.path.getsize(audio_file) < 1000:  # 小于1KB的文件可能有问题
                    logger.warning(f"录音文件过小，可能没有录到声音: {audio_file}")
                    return None
                
                # 使用更安全的方式调用whisper transcribe
                try:
                    # 创建临时文件，避免文件锁定问题
                    temp_file = audio_file + ".temp"
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                    
                    # 复制一份文件进行处理
                    shutil.copy2(audio_file, temp_file)
                    
                    # 转录文件
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
                        
                    # 处理结果
                    if isinstance(result, dict) and 'text' in result:
                        text = result['text'].strip()
                        if text:
                            logger.info(f"语音识别结果: {text}")
                            return text
                        else:
                            logger.info("语音识别结果为空")
                            return None
                    else:
                        logger.warning(f"语音识别结果格式异常: {type(result)}")
                        return None
                        
                except Exception as e:
                    logger.warning(f"Whisper转录过程出错: {e}")
                    return None
                    
            else:
                logger.warning(f"录音文件不存在: {audio_file}")
            return None
            
        except Exception as e:
            logger.warning(f"语音识别失败: {e}")
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
            
            # 清空转录队列
            while not self.transcription_queue.empty():
                self.transcription_queue.get()
            
            # 重置通知标志
            self.notified_new_transcription = False
            
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
    
    def has_new_transcription(self):
        """检查是否有新的转录结果
        
        Returns:
            bool: 是否有新的转录结果
        """
        return not self.transcription_queue.empty()
    
    def get_next_transcription(self):
        """获取下一个转录结果，如果队列为空则返回None
        
        Returns:
            str or None: 下一个转录结果
        """
        try:
            if self.transcription_queue.empty():
                return None
            text = self.transcription_queue.get(block=False)
            return text
        except queue.Empty:
            return None
    
    def get_all_transcriptions(self):
        """获取所有转录结果
        
        Returns:
            list: 所有转录结果的列表
        """
        results = []
        try:
            while not self.transcription_queue.empty():
                results.append(self.transcription_queue.get(block=False))
        except queue.Empty:
            pass
        return results
    
    def _realtime_transcription_loop(self):
        """实时转录循环"""
        try:
            logger.info(f"开始实时转录循环，监控录音文件: {self.recording_file}")
            last_size = 0
            last_transcription_time = time.time()
            min_chunk_size = 8000  # 至少8KB新数据才处理
            segment_count = 0
            
            # 等待录音文件创建
            while self.transcriber_active and not os.path.exists(self.recording_file):
                logger.info(f"等待录音文件创建: {self.recording_file}")
                time.sleep(0.5)
            
            if not os.path.exists(self.recording_file):
                logger.warning(f"录音文件未创建: {self.recording_file}")
                return
                
            logger.info(f"录音文件已创建，开始监控: {self.recording_file}")
            
            # 主循环
            while self.transcriber_active:
                try:
                    # 检查文件是否存在
                    if not os.path.exists(self.recording_file):
                        logger.warning(f"录音文件已消失: {self.recording_file}")
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
                            
                            # 使用AudioUtils预处理音频，确保格式正确
                            processed_file = os.path.join(segment_dir, f"processed_{segment_count}.wav")
                            try:
                                # 使用AudioUtils转换音频格式为Whisper兼容格式(16kHz)
                                processed_wav = AudioUtils.ensure_sip_compatible_format(
                                    segment_file, 
                                    processed_file, 
                                    sample_rate=16000,  # Whisper通常使用16kHz
                                    channels=1
                                )
                                
                                if processed_wav and os.path.exists(processed_wav):
                                    logger.info(f"音频预处理成功: {processed_wav}")
                                    
                                    # 转录处理
                                    text = self._transcribe_segment(processed_wav, segment_count)
                                    
                                    # 如果成功识别到文本，将其添加到转录队列
                                    if text:
                                        logger.info(f"将转录结果添加到队列: '{text}'")
                                        self.transcription_queue.put(text)
                                        
                                        # 通知有新的转录结果
                                        if self.response_callback:
                                            self.response_callback(text)
                                            # 标记已通知
                                            self.notified_new_transcription = True
                                else:
                                    logger.info(f"预处理后的音频文件过小或不存在: {processed_file}")
                            except Exception as e:
                                logger.warning(f"音频预处理失败: {e}")
                            
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
                                logger.info(f"无法删除临时文件: {e}")
                            
                        except Exception as e:
                            logger.warning(f"处理音频段 {segment_count} 时出错: {e}")
                    
                    # 短暂休眠
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.warning(f"实时转录循环出错: {e}")
                    time.sleep(1)
            
            logger.info("实时转录循环结束")
            
        except Exception as e:
            logger.warning(f"实时转录线程出错: {e}")
        
        self.transcriber_active = False
    
    def _transcribe_segment(self, processed_file, segment_count):
        """转录单个音频段，简化错误处理"""
        if not self.whisper_model:
            logger.warning("Whisper模型未加载，无法进行语音识别")
            return None
        
        # 判断是否有实际的人声，只有有效的语音段才会触发响应
        # 这是为了过滤背景噪音和无意义的声音
        min_meaningful_length = 3  # 至少3个字符才认为是有效语音
        
        try:
            # 直接转录文件，不使用复杂的重试机制
            logger.info(f"尝试转录音频段 {segment_count}")
            result = self.whisper_model.transcribe(
                processed_file,
                language="zh",
                fp16=False
            )
            text = result.get("text", "").strip()
            
            if text:
                # 检查文本长度，过滤掉太短的可能是噪音的内容
                if len(text) >= min_meaningful_length:
                    logger.info(f"语音识别结果 (段{segment_count}): {text} - 有效语音")
                    return text
                else:
                    logger.info(f"语音识别结果过短，可能是噪音 (段{segment_count}): {text}")
                    return None
            else:
                logger.info(f"语音识别结果为空 (段{segment_count})")
                return None
                
        except Exception as e:
            # 简化错误处理，只记录警告日志
            logger.warning(f"转录过程出错: {e}")
            return None 