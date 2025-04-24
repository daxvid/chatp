import whisper
import os
from pathlib import Path
import logging
import time
import traceback
import torch  # 添加torch导入

logger = logging.getLogger("whisper")

class WhisperManager:
    def __init__(self, model_size="turbo", model_dir="models/whisper", use_gpu=True):
        """Whisper语音识别管理器
        
        Args:
            model_size: 模型大小 (tiny, base, small, medium, large, turbo)
            model_dir: 模型存储目录
            use_gpu: 是否使用GPU加速
        """
        self.model_size = model_size
        self.model_dir = Path(model_dir)
        self.model = None
        
        # 设置设备（CPU或GPU）
        self.use_gpu = use_gpu and torch.cuda.is_available()
        self.device = "cuda" if self.use_gpu else "cpu"
        
        if self.use_gpu:
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"启用GPU加速，使用 {gpu_name}")
        else:
            logger.info("使用CPU模式")
            
        self.load_model()
        
        
    def load_model(self):
        """加载Whisper模型"""
        try:
            # 创建模型目录
            self.model_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"正在加载Whisper模型({self.model_size})到{self.device}...")
            self.model = whisper.load_model(self.model_size, device=self.device, download_root=str(self.model_dir))
            logger.info("Whisper模型加载成功")
            return True
        except Exception as e:
            logger.error(f"加载Whisper模型失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False
    
    def transcribe(self, audio_file):
        """执行转录任务的线程函数"""
        try:
            if not self.model:
                logger.error("Whisper模型未加载")
                return None
                
            if not os.path.exists(audio_file):
                logger.error(f"音频文件不存在: {audio_file}")
                return None
                
            logger.info(f"开始转录音频: {audio_file}")
            start_time = time.time()
            result = self.model.transcribe(
                audio_file,
                language="zh",
                fp16=self.use_gpu  # 启用半精度浮点加速
            )
            
            # 确保GPU操作完成
            if self.use_gpu:
                torch.cuda.synchronize()
                
            duration = time.time() - start_time
            logger.info(f"转录完成({duration:.2f}秒): {result['text'][:50]}...")
            
            return result
        except Exception as e:
            logger.error(f"转录音频失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
            
    def shutdown(self):
        # 如果使用GPU，清理缓存
        if self.use_gpu:
            torch.cuda.empty_cache()