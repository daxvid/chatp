import os
import time
import json
import redis
import whisper
import logging
import torch
import threading
import queue
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("whisper_main")

class WhisperTranscriptionWorker:
    def __init__(self, model_size="turbo", model_dir="models/whisper", redis_host="localhost", redis_port=6379, max_workers=4):
        """初始化转录工作进程
        
        Args:
            model_size: Whisper模型大小
            model_dir: 模型存储目录
            redis_host: Redis服务器地址
            redis_port: Redis服务器端口
            max_workers: 最大工作线程数
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
        
        # 线程池
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # 任务队列和锁
        self.task_queue = queue.Queue()
        self.task_lock = threading.Lock()
        self.active_tasks = set()
        self.active_tasks_lock = threading.Lock()
        
        # 加载模型
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
            return False
    
    def transcribe_audio(self, audio_file, task_id):
        """转录音频文件
        
        Args:
            audio_file: 音频文件路径
            task_id: 任务ID
            
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
                
            logger.info(f"开始转录音频: {audio_file}")
            start_time = time.time()
            
            # 使用线程锁确保模型访问的线程安全
            with self.task_lock:
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
            return None
        finally:
            # 从活动任务集合中移除
            with self.active_tasks_lock:
                self.active_tasks.remove(task_id)
    
    def process_task(self, task_info):
        """处理单个转录任务
        
        Args:
            task_info: 任务信息字典
        """
        task_id = task_info["task_id"]
        audio_file = task_info["audio_file"]
        
        try:
            # 将任务ID添加到活动任务集合
            with self.active_tasks_lock:
                self.active_tasks.add(task_id)
            
            # 执行转录
            result = self.transcribe_audio(audio_file, task_id)
            # 将结果写入Redis
            if result:
                self.redis_client.setex(
                    f"tran:{task_id}",
                    2592000,  # 30 days timeout
                    json.dumps({
                        "success": True,
                        "text": result["text"],
                        "segments": result.get("segments", [])
                    }, ensure_ascii=False)
                )
            else:
                self.redis_client.setex (
                    f"tran:{task_id}",
                    2592000,  # 30 days timeout
                    json.dumps({
                        "success": False,
                        "error": "Transcription failed"
                    }, ensure_ascii=False)
                )
            
            logger.info(f"文件 {audio_file} 处理完成")
            
        except Exception as e:
            logger.error(f"处理文件 {audio_file} 时发生错误: {e}")
            # 确保错误结果也被写入Redis
            self.redis_client.setex(
                f"tran:{task_id}",  
                2592000,  # 30 days timeout
                json.dumps({
                    "success": False,
                    "error": str(e)
                }, ensure_ascii=False)
            )
    
    def run(self):
        """运行转录工作进程"""
        logger.info(f"转录工作进程启动，最大工作线程数: {self.max_workers}")
        
        while True:
            try:
                # 从Redis队列中获取待转录任务
                task = self.redis_client.blpop("whisper_tasks", timeout=1)
                
                if task:
                    # 解析任务数据
                    _, task_data = task
                    task_info = json.loads(task_data)
                    
                    # 提交任务到线程池
                    self.executor.submit(self.process_task, task_info)
                
            except Exception as e:
                logger.error(f"处理任务时发生错误: {e}")
                time.sleep(1)  # 发生错误时短暂等待
    
    def shutdown(self):
        """关闭转录工作进程"""
        logger.info("正在关闭转录工作进程...")
        
        # 等待所有活动任务完成
        with self.active_tasks_lock:
            active_count = len(self.active_tasks)
        if active_count > 0:
            logger.info(f"等待 {active_count} 个活动任务完成...")
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        # 清理GPU缓存
        if self.use_gpu:
            torch.cuda.empty_cache()
        
        logger.info("转录工作进程已关闭")

def main():
    """主函数"""
    import multiprocessing

    # 从环境变量获取配置
    model_size = os.getenv("WHISPER_MODEL_SIZE", "turbo")
    model_dir = os.getenv("WHISPER_MODEL_DIR", "models/whisper")
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    max_workers = int(os.getenv("WHISPER_MAX_WORKERS", "0"))

    if max_workers == 0:
        # 获取CPU核心数
        cpu_count = multiprocessing.cpu_count()
        max_workers = cpu_count // 2
        if max_workers == 0:
            max_workers = 1
    
    # 创建并运行转录工作进程
    worker = WhisperTranscriptionWorker(
        model_size=model_size,
        model_dir=model_dir,
        redis_host=redis_host,
        redis_port=redis_port,
        max_workers=max_workers
    )
    
    try:
        worker.run()
    except KeyboardInterrupt:
        logger.info("收到终止信号，正在关闭...")
        worker.shutdown()
    except Exception as e:
        logger.error(f"发生错误: {e}")
        worker.shutdown()

if __name__ == "__main__":
    main()
