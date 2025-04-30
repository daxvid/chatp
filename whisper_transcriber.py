import os
import time
from datetime import datetime
import logging
import shutil
import threading
import subprocess
import traceback

logger = logging.getLogger("sip")

class WhisperTranscriber:
    """Whisper语音转文本处理类"""
    
    def __init__(self):
        pass
    
    def transcribe_file(self, audio_file, segment_count=0):
        """转录单个音频文件"""
        start_time = time.time()
        try:    
            if not audio_file or not os.path.exists(audio_file):
                logger.error(f"音频文件不存在: {audio_file}")
                return None
                
            # 检查文件大小，确保不是空文件
            if os.path.getsize(audio_file) < 1000:  # 小于1KB的文件可能有问题
                logger.warning(f"录音文件过小，可能没有录到声音: {audio_file}")
                return None
            
            # 使用临时文件处理，避免文件锁定问题
            temp_file = None
            success = False
            try:
                # 创建第一个临时文件，在扩展名前加temp
                timestamp = datetime.now().strftime("_%H%M%S")
                base_name, ext = os.path.splitext(audio_file)
                temp_file = f"{base_name}{timestamp}.temp{ext}"
                logger.info(f"开始转录: {temp_file}")
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                
                # 使用ffmpeg去掉静音
                # ffmpeg -i input.wav -af silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-50dB output.wav
                ffmpeg_command = f"ffmpeg -i {audio_file} -af silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-50dB {temp_file}"
                subprocess.run(ffmpeg_command, shell=True, check=True)
                
                # 使用Whisper模型进行转录
                text = self.whisper_manager.transcribe_and_wait_result(temp_file)
                
                # 记录处理时间
                duration = time.time() - start_time
                logger.info(f"转录耗时: {duration:.2f}秒")
                success = True
                if text:
                    logger.info(f"转录结果: {text}")
                    return text
                else:
                    logger.info("转录结果为空")
                    return None
                    
            except Exception as e:
                logger.error(f"转录失败: {e}")
                #logger.error(f"详细错误: {traceback.format_exc()}")
                return None
                
            finally:
                # 清理临时文件
                if success and temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception as e:
                        logger.warning(f"清理临时文件失败: {e}")
                        
        except Exception as e:
            logger.error(f"处理音频文件时出错: {e}")
            return None

    def transcribe_file2(self, audio_file):
        """转录单个音频文件 - 异步版本，使用WhisperManager的线程池"""
        try:
            start_time = time.time()
            text = self.whisper_manager.transcribe_and_wait_result(audio_file)
            # 记录处理时间
            duration = time.time() - start_time
            logger.info(f"转录耗时: {duration:.2f}秒")
            if text:
                logger.info(f"转录结果: {text}")
                return text
            else:
                logger.info("转录结果为空")
                return None
        except Exception as e:
            logger.error(f"转录失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
                        