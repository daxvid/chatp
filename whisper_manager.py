import whisper
import os
from pathlib import Path
import logging
import threading
import concurrent.futures
import time
from collections import OrderedDict
import traceback

logger = logging.getLogger("whisper")

class ThreadSafeDict:
    """线程安全的字典实现"""
    def __init__(self, max_size=100):
        self.lock = threading.RLock()
        self.cache = OrderedDict()
        self.max_size = max_size
        
    def get(self, key, default=None):
        """获取缓存值"""
        with self.lock:
            try:
                value = self.cache.get(key, default)
                return value
            except Exception as e:
                logger.error(f"获取缓存出错: {e}")
                return default
                
    def set(self, key, value):
        """设置缓存值"""
        with self.lock:
            try:
                # 如果达到最大容量，移除最早的项
                if len(self.cache) >= self.max_size:
                    self.cache.popitem(last=False)
                self.cache[key] = value
            except Exception as e:
                logger.error(f"设置缓存出错: {e}")
                
    def remove(self, key):
        """移除缓存项"""
        with self.lock:
            try:
                if key in self.cache:
                    del self.cache[key]
                    return True
                return False
            except Exception as e:
                logger.error(f"移除缓存出错: {e}")
                return False
                
    def has_key(self, key):
        """检查是否存在键"""
        with self.lock:
            return key in self.cache

class WhisperManager:
    def __init__(self, model_size="turbo", model_dir="models/whisper", max_workers=3):
        """Whisper语音识别管理器"""
        self.model_size = model_size
        self.model_dir = Path(model_dir)
        self.model = None
        self.load_model()
        
        # 创建线程池
        self.max_workers = max_workers
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        
        # 创建线程安全的结果缓存
        self.results_cache = ThreadSafeDict(max_size=200)
        self.futures = {}  # 跟踪正在处理的任务
        self.futures_lock = threading.RLock()  # 用于futures字典的锁
        
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
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False
    
    def _transcribe_task(self, audio_file):
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
                fp16=True
            )
            duration = time.time() - start_time
            logger.info(f"转录完成({duration:.2f}秒): {result['text'][:50]}...")
            
            # 存储结果到缓存
            self.results_cache.set(audio_file, result)
            
            return result
        except Exception as e:
            logger.error(f"转录音频失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
            
    def transcribe(self, audio_file):
        """异步转录音频文件，立即返回，结果稍后可通过get_result获取"""
        try:
            # 检查是否已经在处理中
            with self.futures_lock:
                if audio_file in self.futures and not self.futures[audio_file].done():
                    logger.info(f"音频 {audio_file} 已在处理队列中")
                    return True
                    
            # 检查是否已有结果
            if self.results_cache.has_key(audio_file):
                logger.info(f"音频 {audio_file} 已有转录结果")
                return True
            
            # 提交新任务到线程池
            logger.info(f"提交音频 {audio_file} 到转录队列")
            future = self.executor.submit(self._transcribe_task, audio_file)
            
            # 存储Future对象
            with self.futures_lock:
                self.futures[audio_file] = future
                
            return True
        except Exception as e:
            logger.error(f"提交转录任务失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False
            
    def get_result(self, audio_file, remove_after=False):
        """获取转录结果，如果结果尚未准备好，返回None
        
        Args:
            audio_file: 音频文件路径
            remove_after: 是否在获取后从缓存中移除结果
            
        Returns:
            转录结果或None（如果尚未完成）
        """
        try:
            # 首先检查缓存中是否有结果
            result = self.results_cache.get(audio_file)
            if result:
                logger.info(f"从缓存获取音频 {audio_file} 的转录结果")
                if remove_after:
                    self.results_cache.remove(audio_file)
                return result
                
            # 检查任务是否在进行中
            with self.futures_lock:
                future = self.futures.get(audio_file)
                
            if not future:
                logger.info(f"音频 {audio_file} 的转录任务不存在")
                return None
                
            # 检查任务是否完成
            if not future.done():
                logger.info(f"音频 {audio_file} 的转录任务尚未完成")
                return None
                
            # 获取结果
            try:
                result = future.result(timeout=0.1)  # 立即返回结果，不等待
                logger.info(f"获取音频 {audio_file} 的转录结果")
                
                # 清理future记录
                with self.futures_lock:
                    if audio_file in self.futures:
                        del self.futures[audio_file]
                        
                # 如果需要，从缓存中移除
                if remove_after and result:
                    self.results_cache.remove(audio_file)
                    
                return result
            except concurrent.futures.TimeoutError:
                logger.info(f"获取音频 {audio_file} 的转录结果超时")
                return None
        except Exception as e:
            logger.error(f"获取转录结果失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None

    def is_transcription_complete(self, audio_file):
        """检查转录任务是否完成
        
        Args:
            audio_file: 音频文件路径
            
        Returns:
            布尔值，表示转录是否完成
        """
        # 检查缓存
        if self.results_cache.has_key(audio_file):
            return True
            
        # 检查任务是否在进行中
        with self.futures_lock:
            future = self.futures.get(audio_file)
            
        # 如果任务不存在，则认为转录完成,防止处部检查死循环
        if not future:
            return True
            
        return future.done()
        
    def transcribe_and_wait_result(self, audio_file):
        """转录音频文件并获取结果"""
        if self.transcribe(audio_file):
            while not self.is_transcription_complete(audio_file):
                time.sleep(0.1)
            return self.get_result(audio_file,True)
        else:
            return None
        
    def shutdown(self):
        """关闭线程池"""
        logger.info("正在关闭Whisper转录线程池...")
        self.executor.shutdown(wait=True)
        logger.info("Whisper转录线程池已关闭") 