import whisper
import os
from pathlib import Path
import logging

logger = logging.getLogger("whisper")

class WhisperManager:
    def __init__(self, model_size="small", model_dir="models/whisper"):
        """Whisper语音识别管理器"""
        self.model_size = model_size
        self.model_dir = Path(model_dir)
        self.model = None
        self.load_model()
        
    def load_model(self):
        """加载Whisper模型"""
        try:
            # 创建模型目录
            self.model_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"正在加载Whisper模型({self.model_size})...")
            self.model = whisper.load_model(self.model_size, download_root=str(self.model_dir))
            logger.info("Whisper模型加载成功")
            return True
        except Exception as e:
            logger.error(f"加载Whisper模型失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False
            
    def transcribe(self, audio_file):
        """转录音频文件"""
        try:
            if not self.model:
                logger.error("Whisper模型未加载")
                return None
                
            if not os.path.exists(audio_file):
                logger.error(f"音频文件不存在: {audio_file}")
                return None
                
            logger.info(f"开始转录音频: {audio_file}")
            result = self.model.transcribe(audio_file)
            logger.info(f"转录完成: {result['text'][:50]}...")
            return result
        except Exception as e:
            logger.error(f"转录音频失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None 