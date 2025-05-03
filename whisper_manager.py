import whisper
import os
from pathlib import Path
import logging
import time
import traceback
import torch  # 添加torch导入
import json
import redis
import uuid

logger = logging.getLogger("whisper")

class WhisperManager:
    def __init__(self, model_size="turbo", model_dir="models/whisper", redis_host="localhost", redis_port=6379):
        """Whisper转录管理器
        
        Args:
            model_size: 模型大小 (tiny, base, small, medium, large, turbo)
            model_dir: 模型存储目录
            redis_host: Redis服务器地址
            redis_port: Redis服务器端口
        """
        self.model_size = model_size
        self.model_dir = Path(model_dir)
        self.model = None
        
        # 设置设备（CPU或GPU）
        self.use_gpu = torch.cuda.is_available()
        self.device = "cuda" if self.use_gpu else "cpu"
        
        if self.use_gpu:
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"启用GPU加速，使用 {gpu_name}")
        else:
            logger.info("使用CPU模式")
            
        # 初始化Redis连接
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True  # 自动解码响应为字符串
        )
        
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
    
    def transcribe(self, audio_file, timeout=300):
        """提交转录任务并等待结果
        
        Args:
            audio_file: 音频文件路径
            timeout: 等待结果超时时间（秒）
            
        Returns:
            dict: 转录结果
        """
        try:
            if not self.model:
                logger.error("Whisper模型未加载")
                return None
                
            if not os.path.exists(audio_file):
                logger.error(f"音频文件不存在: {audio_file}")
                return None
                
            # 生成任务ID
            task_id = str(uuid.uuid4())
            
            # 创建任务数据
            task_data = {
                "task_id": task_id,
                "audio_file": audio_file
            }
            
            # 将任务写入Redis队列
            logger.info(f"提交转录任务 {task_id}: {audio_file}")
            self.redis_client.rpush("whisper_tasks", json.dumps(task_data))
            
            # 等待结果
            start_time = time.time()
            while time.time() - start_time < timeout:
                # 检查结果是否已就绪
                result_data = self.redis_client.get(f"whisper_result:{task_id}")
                if result_data:
                    result = json.loads(result_data)
                    # 清理结果数据
                    self.redis_client.delete(f"whisper_result:{task_id}")
                    return result
                time.sleep(0.1)  # 短暂等待后重试
            
            logger.error(f"转录任务 {task_id} 超时")
            return None
                
        except Exception as e:
            logger.error(f"提交转录任务失败: {e}")
            return None
            
    def shutdown(self):
        """关闭管理器"""
        # 如果使用GPU，清理缓存
        if self.use_gpu:
            torch.cuda.empty_cache()