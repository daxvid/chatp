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
    
    def set_model(self, model):
        """设置Whisper模型"""
        self.whisper_model = model
    
    def transcribe_file(self, audio_file, segment_count=0):
        """语音识别单个音频文件"""
        try:
            if not self.whisper_model:
                logger.error("Whisper模型未加载，无法进行语音识别")
                return None
                
            if audio_file and os.path.exists(audio_file):
                # 检查文件大小，确保不是空文件
                if os.path.getsize(audio_file) < 1000:  # 小于1KB的文件可能有问题
                    logger.warning(f"录音文件过小，可能没有录到声音: {audio_file}")
                    return None

                logger.info(f"开始语音识别: {audio_file}")
                try:
                    # 使用原始文件直接转录文
                    result = self.whisper_model.transcribe(
                        audio_file,
                        language="zh",
                        fp16=False
                    )
                    text = result.get("text", "").strip()
                    if text:
                        logger.info(f"语音识别结果: {text}")
                        return text
                    else:
                        logger.info(f"语音识别结果为空")
                        return None
                except Exception as e:
                    logger.warning(f"语音识别失败:{audio_file} {e}")
                    try:
                        # 确保处理前没有其他程序占用文件
                        temp_file = audio_file + ".temp"
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                        # 复制一份文件进行处理，避免文件锁定问题
                        shutil.copy2(audio_file, temp_file)
                        # 使用原始方法直接转录文
                        result = self.whisper_model.transcribe(
                            temp_file,
                            language="zh",
                            fp16=False
                        )
                        # 清理临时文件
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                            
                        text = result.get("text", "").strip()
                        if text:
                            logger.info(f"语音识别结果: {text}")
                            return text
                        else:
                            logger.info(f"语音识别结果为空")
                            return None
                    except Exception as e:
                        logger.error(f"语音识别失败::{audio_file} {e}")
                        logger.error(f"详细错误: {traceback.format_exc()}")
            else:
                logger.warning(f"录音文件不存在: {audio_file}")
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
        return None