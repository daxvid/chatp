import os
import time
import logging
import shutil
import threading
import subprocess
import traceback
import wave
import queue
import tempfile
import datetime
from concurrent.futures import ThreadPoolExecutor

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

logger = logging.getLogger("whisper")

class WhisperTranscriber:
    """Whisper语音转写类"""
    def __init__(self, model):
        """初始化Whisper转写器"""
        self.model = model
        self.is_running = False
        self.transcription_thread = None
        self.transcription_results = []
        self.transcription_queue = queue.Queue()
        self.response_callback = None
        self.play_response_callback = None
        self.logger = logging.getLogger("whisper")  # 添加logger实例
        
        # 用于分段的参数
        self.segment_duration = 10  # 每段10秒
        self.min_silence_duration = 0.5  # 最小静音时长(秒)
        self.silence_threshold = 0.05  # 静音阈值
    
    def _read_wav_data(self, wav_file):
        """读取WAV文件数据"""
        try:
            # 验证文件是否存在
            if not os.path.exists(wav_file):
                self.logger.error(f"WAV文件不存在: {wav_file}")
                return None, None, None
                
            # 验证文件是否为WAV格式
            try:
                with open(wav_file, 'rb') as f:
                    header = f.read(4)
                    if header != b'RIFF':
                        self.logger.error(f"文件不是有效的WAV格式: {wav_file}")
                        return None, None, None
            except Exception as e:
                self.logger.error(f"读取文件头失败: {e}")
                return None, None, None
                
            # 打开WAV文件并读取音频数据
            with wave.open(wav_file, 'rb') as wf:
                frames = wf.getnframes()
                if frames == 0:
                    self.logger.error(f"WAV文件没有音频帧: {wav_file}")
                    return None, None, None
                    
                rate = wf.getframerate()
                duration = frames / rate
                
                # 读取所有数据
                raw_data = wf.readframes(frames)
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                
                # 转换为numpy数组以便处理
                dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.float32)
                data = np.frombuffer(raw_data, dtype=dtype)
                
                # 如果是双声道，转换为单声道
                if channels == 2:
                    data = data.reshape(-1, 2).mean(axis=1)
                
                return data, rate, duration
                
        except Exception as e:
            self.logger.error(f"读取WAV文件失败: {e}")
            import traceback
            self.logger.error(f"详细错误: {traceback.format_exc()}")
            return None, None, None
    
    def _segment_audio_file(self, input_file, output_dir=None):
        """将音频文件分段，以便并行转录
        
        Args:
            input_file: 输入音频文件路径
            output_dir: 输出目录，默认为临时目录
            
        Returns:
            list: 分段后的文件路径列表
        """
        try:
            # 创建输出目录
            if not output_dir:
                output_dir = tempfile.mkdtemp(prefix="whisper_segments_")
            else:
                os.makedirs(output_dir, exist_ok=True)
                
            self.logger.info(f"将音频文件分段: {input_file} -> {output_dir}")
            
            # 分析输入文件
            data, sample_rate, duration = self._read_wav_data(input_file)
            if data is None:
                return []
                
            self.logger.info(f"音频长度: {duration:.2f}秒, 采样率: {sample_rate}")
            
            # 如果文件太短，不需要分段
            if duration <= self.segment_duration:
                segment_file = os.path.join(output_dir, "segment_0.wav")
                # 复制原始文件
                with open(input_file, 'rb') as src, open(segment_file, 'wb') as dst:
                    dst.write(src.read())
                return [segment_file]
                
            # 将数据按振幅标准化
            data = data.astype(np.float32)
            if np.max(np.abs(data)) > 0:  # 避免除零
                data = data / np.max(np.abs(data))
            
            # 计算能量
            frame_length = int(sample_rate * 0.025)  # 25ms窗口
            hop_length = int(sample_rate * 0.010)    # 10ms步长
            energy = []
            
            for i in range(0, len(data) - frame_length, hop_length):
                frame = data[i:i+frame_length]
                energy.append(np.mean(frame**2))
            
            # 检测静音
            is_silence = np.array(energy) < self.silence_threshold
            
            # 找到静音段的开始和结束
            silence_starts = []
            silence_ends = []
            prev_silence = False
            
            for i, silence in enumerate(is_silence):
                if silence and not prev_silence:
                    silence_starts.append(i)
                elif not silence and prev_silence:
                    silence_ends.append(i)
                prev_silence = silence
                
            # 确保列表长度匹配
            if len(silence_starts) > len(silence_ends):
                silence_ends.append(len(is_silence))
            
            # 计算静音持续时间
            silence_durations = []
            for start, end in zip(silence_starts, silence_ends):
                duration_sec = (end - start) * hop_length / sample_rate
                if duration_sec >= self.min_silence_duration:
                    silence_durations.append((start, end, duration_sec))
            
            # 根据静音点分段
            segments = []
            start_sample = 0
            segment_count = 0
            
            for start, end, duration_sec in silence_durations:
                # 计算采样点位置
                mid_silence = (start + end) // 2
                end_sample = mid_silence * hop_length
                
                # 如果段长度超过目标段长度，则创建一个段
                if (end_sample - start_sample) / sample_rate >= self.segment_duration:
                    # 创建段
                    segment_file = os.path.join(output_dir, f"segment_{segment_count}.wav")
                    segments.append(segment_file)
                    
                    # 写入WAV文件
                    with wave.open(segment_file, 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)  # 16位
                        wf.setframerate(sample_rate)
                        
                        # 将float32数据转换回int16
                        segment_data = data[start_sample:end_sample]
                        int16_data = (segment_data * 32767).astype(np.int16)
                        wf.writeframes(int16_data.tobytes())
                    
                    self.logger.info(f"创建段 {segment_count}: {(end_sample - start_sample) / sample_rate:.2f}秒")
                    
                    # 更新起始点
                    start_sample = end_sample
                    segment_count += 1
            
            # 处理最后一段
            if start_sample < len(data):
                segment_file = os.path.join(output_dir, f"segment_{segment_count}.wav")
                segments.append(segment_file)
                
                # 写入WAV文件
                with wave.open(segment_file, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16位
                    wf.setframerate(sample_rate)
                    
                    # 将float32数据转换回int16
                    segment_data = data[start_sample:]
                    int16_data = (segment_data * 32767).astype(np.int16)
                    wf.writeframes(int16_data.tobytes())
                
                self.logger.info(f"创建段 {segment_count}: {(len(data) - start_sample) / sample_rate:.2f}秒")
            
            # 如果没有成功分段，返回原始文件
            if not segments:
                segment_file = os.path.join(output_dir, "segment_0.wav")
                # 复制原始文件
                with open(input_file, 'rb') as src, open(segment_file, 'wb') as dst:
                    dst.write(src.read())
                segments = [segment_file]
                
            self.logger.info(f"分段完成，共 {len(segments)} 个段")
            return segments
            
        except Exception as e:
            self.logger.error(f"分段失败: {e}")
            import traceback
            self.logger.error(f"详细错误: {traceback.format_exc()}")
            return []
    
    def transcribe_file(self, file_path):
        """转录整个音频文件"""
        try:
            self.logger.info(f"开始转录文件: {file_path}")
            
            # 确保输入文件格式正确
            if not os.path.exists(file_path):
                self.logger.error(f"文件不存在: {file_path}")
                return None
            
            # 检查文件扩展名
            if not file_path.lower().endswith('.wav'):
                self.logger.error(f"只支持WAV格式: {file_path}")
                return None
                
            # 检查文件是否有效的WAV文件
            try:
                with wave.open(file_path, 'rb') as wf:
                    if wf.getnframes() == 0:
                        self.logger.error(f"WAV文件没有有效音频帧: {file_path}")
                        return None
            except Exception as e:
                self.logger.error(f"无法打开WAV文件: {e}")
                return None
                
            # 创建临时目录存放分段文件
            segment_dir = tempfile.mkdtemp(prefix="whisper_segments_")
            
            # 分段处理
            segments = self._segment_audio_file(file_path, segment_dir)
            if not segments:
                self.logger.error(f"分段失败，无法转录: {file_path}")
                return None
                
            # 使用线程池并行转录分段
            results = []
            
            with ThreadPoolExecutor(max_workers=min(os.cpu_count(), len(segments))) as executor:
                futures = []
                
                for i, segment_file in enumerate(segments):
                    futures.append(
                        executor.submit(self._transcribe_segment, segment_file, i)
                    )
                
                # 收集结果
                for future in futures:
                    result = future.result()
                    if result:
                        results.append(result)
            
            # 合并结果
            combined_text = " ".join(results)
            self.logger.info(f"转录完成: {combined_text[:100]}...")
            
            # 清理临时文件
            for segment in segments:
                try:
                    os.remove(segment)
                except:
                    pass
            try:
                os.rmdir(segment_dir)
            except:
                pass
                
            return combined_text
            
        except Exception as e:
            self.logger.error(f"转录失败: {e}")
            import traceback
            self.logger.error(f"详细错误: {traceback.format_exc()}")
            return None
    
    def _transcribe_segment(self, segment_file, segment_count):
        """转录单个音频段"""
        try:
            self.logger.info(f"开始转录段 {segment_count}: {segment_file}")
            
            # 获取段目录
            segment_dir = os.path.dirname(segment_file)
            
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
                    self.logger.info(f"音频预处理成功: {processed_wav}")
                    
                    # 转录处理
                    text = self._transcribe_with_whisper(processed_wav)
                    
                    # 如果转录成功，返回文本
                    if text:
                        self.logger.info(f"段 {segment_count} 转录成功: {text[:50]}...")
                        return text
                    else:
                        self.logger.error(f"段 {segment_count} 转录失败")
                        return ""
                else:
                    self.logger.error(f"音频预处理失败: {segment_file}")
                    return ""
            except Exception as e:
                self.logger.error(f"预处理或转录段 {segment_count} 时出错: {e}")
                import traceback
                self.logger.error(f"详细错误: {traceback.format_exc()}")
                return ""
                
        except Exception as e:
            self.logger.error(f"转录段 {segment_count} 失败: {e}")
            import traceback
            self.logger.error(f"详细错误: {traceback.format_exc()}")
            return ""
    
    def _transcribe_with_whisper(self, audio_file):
        """使用Whisper模型转录音频"""
        try:
            self.logger.info(f"使用Whisper转录: {audio_file}")
            
            # 执行转录
            result = self.model.transcribe(
                audio_file,
                language="zh"  # 指定中文可提高准确性
            )
            
            if 'text' in result:
                text = result['text'].strip()
                self.logger.info(f"Whisper转录结果: {text[:100]}...")
                return text
            else:
                self.logger.warning(f"未获取到转录文本")
                return ""
                
        except Exception as e:
            self.logger.error(f"Whisper转录失败: {e}")
            import traceback
            self.logger.error(f"详细错误: {traceback.format_exc()}")
            return ""
            
    def start_realtime_transcription(self, wav_file, response_callback=None, play_response_callback=None):
        """启动实时转录线程
        
        Args:
            wav_file: 要监控的WAV文件路径
            response_callback: 接收转录结果的回调函数
            play_response_callback: 播放响应的回调函数
        """
        try:
            if self.is_running:
                self.logger.warning("实时转录已在运行")
                return False
                
            self.transcription_results = []
            self.response_callback = response_callback
            self.play_response_callback = play_response_callback
            self.is_running = True
            
            # 启动转录线程
            self.transcription_thread = threading.Thread(
                target=self._process_wav_file,
                args=(wav_file,),
                daemon=True
            )
            self.transcription_thread.start()
            
            self.logger.info(f"实时转录线程已启动，监控文件: {wav_file}")
            return True
        except Exception as e:
            self.logger.error(f"启动实时转录失败: {e}")
            self.is_running = False
            return False
            
    def _process_wav_file(self, source_file):
        """处理WAV文件，进行转换、分析和转写"""
        try:
            # 检查源文件是否存在
            if not os.path.exists(source_file):
                self.logger.error(f"源文件不存在: {source_file}")
                return "", 0
                
            # 读取音频数据
            data, sr, duration = self._read_wav_data(source_file)
            if data is None:
                self.logger.error(f"无法从文件中读取有效的WAV数据: {source_file}")
                return "", 0
                
            # 记录原始音频时长
            self.logger.info(f"原始音频时长: {duration:.2f}秒")
            
            # 进行静音检测并获取语音段
            speech_segments = self._detect_speech_segments(data, sr)
            if not speech_segments:
                self.logger.info("未检测到有效语音段")
                return "", 0
                
            # 仅保留语音部分
            total_speech_duration = 0
            speech_only_data = []
            
            for start, end in speech_segments:
                start_idx = int(start * sr)
                end_idx = int(end * sr)
                speech_only_data.append(data[start_idx:end_idx])
                segment_duration = end - start
                total_speech_duration += segment_duration
                
            # 合并所有语音段
            speech_only_data = np.concatenate(speech_only_data)
            
            # 进行转写
            result = self._transcribe_data(speech_only_data, sr)
            
            self.logger.info(f"有效语音时长: {total_speech_duration:.2f}秒")
            
            return result, total_speech_duration
        except Exception as e:
            self.logger.error(f"处理WAV文件时出错: {e}")
            import traceback
            self.logger.error(f"详细错误: {traceback.format_exc()}")
            return "", 0
    
    def stop_transcription(self):
        """停止实时转录"""
        self.is_running = False
        if self.transcription_thread:
            self.transcription_thread.join(timeout=2)
            self.transcription_thread = None
        self.logger.info("实时转录已停止")
        
    def get_transcription_results(self):
        """获取所有转录结果"""
        return self.transcription_results
        
    def get_all_transcriptions(self):
        """从队列获取所有转录结果"""
        results = []
        while not self.transcription_queue.empty():
            try:
                results.append(self.transcription_queue.get_nowait())
            except queue.Empty:
                break
        return results
        
    def has_new_transcription(self):
        """检查是否有新的转录结果"""
        return not self.transcription_queue.empty() 