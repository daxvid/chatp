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
    def __init__(self, redis_host="localhost", redis_port=6379):
        """Whisper转录管理器
        
        Args:
            redis_host: Redis服务器地址
            redis_port: Redis服务器端口
        """
        # 初始化Redis连接
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True  # 自动解码响应为字符串
        )
    
    def transcribe(self, audio_file, timeout=60):
        """提交转录任务并等待结果
        
        Args:
            audio_file: 音频文件路径
            timeout: 等待结果超时时间（秒）
            
        Returns:
            dict: 转录结果
        """
        try:
                
            if not os.path.exists(audio_file):
                logger.error(f"音频文件不存在: {audio_file}")
                return None
                
            # 使用文件名生成任务ID
            task_id = os.path.splitext(os.path.basename(audio_file))[0]
            
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
                result_data = self.redis_client.get(f"tran:{task_id}")
                if result_data:
                    result = json.loads(result_data)
                    return result
                time.sleep(0.1)  # 短暂等待后重试
            
            logger.error(f"转录任务 {task_id} 超时")
            return None
                
        except Exception as e:
            logger.error(f"提交转录任务失败: {e}")
            return None
            