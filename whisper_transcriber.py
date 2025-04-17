import os
import time
from datetime import datetime
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
    
    def set_model(self, model):
        """设置Whisper模型"""
        self.whisper_model = model
    
    def transcribe_file(self, audio_file, segment_count=0):
        """语音识别单个音频文件"""
        start_time = time.time()
        try:
            if not self.whisper_model:
                logger.error("Whisper模型未加载，无法进行语音识别")
                return None
                
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
                logger.info(f"开始语音识别: {temp_file}")
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                
                # 使用ffmpeg去掉静音
                # ffmpeg -i input.wav -af silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-50dB output.wav
                ffmpeg_command = f"ffmpeg -i {audio_file} -af silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-50dB {temp_file}"
                subprocess.run(ffmpeg_command, shell=True, check=True)
                
                # 使用Whisper模型进行转录
                result = self.whisper_model.transcribe(
                    temp_file,
                    language="zh",
                    fp16=False
                )
                
                # 获取转录文本
                text = result.get("text", "").strip()
                
                # 记录处理时间
                duration = time.time() - start_time
                logger.info(f"语音识别耗时: {duration:.2f}秒")
                success = True
                if text:
                    logger.info(f"语音识别结果: {text}")
                    return text
                else:
                    logger.info("语音识别结果为空")
                    return None
                    
            except Exception as e:
                logger.error(f"语音识别失败: {e}")
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
        """语音识别单个音频文件"""
        if not self.whisper_model:
            logger.error("Whisper模型未加载，无法进行语音识别")
            return None
        
        start_time = time.time()
        try:
            # 使用Whisper模型进行转录
            result = self.whisper_model.transcribe(
                audio_file,
                language="zh",
                fp16=False
            )
            # 获取转录文本
            text = result.get("text", "").strip()
            # 记录处理时间
            duration = time.time() - start_time
            logger.info(f"语音识别耗时: {duration:.2f}秒")
            if text:
                logger.info(f"语音识别结果: {text}")
                return text
            else:
                logger.info("语音识别结果为空")
                return None
                
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            return None
                        