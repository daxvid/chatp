import os
import logging
import whisper

logger = logging.getLogger("whisper_manager")

class WhisperManager:
    """Whisper语音识别管理器"""
    def __init__(self, model_size="small", model_dir="models/whisper"):
        """初始化Whisper管理器"""
        self.model_size = model_size
        self.model_dir = model_dir
        self.model = None
        
        # 加载模型
        self._load_model()
        
    def _load_model(self):
        """加载Whisper模型"""
        try:
            # 确保模型目录存在
            os.makedirs(self.model_dir, exist_ok=True)
            
            # 设置模型下载目录
            whisper._download_root = self.model_dir
            
            # 加载模型
            logger.info(f"加载Whisper模型: {self.model_size}")
            self.model = whisper.load_model(self.model_size)
            logger.info(f"Whisper模型加载成功")
            
            return True
        except Exception as e:
            logger.error(f"加载Whisper模型失败: {e}")
            self.model = None
            return False 