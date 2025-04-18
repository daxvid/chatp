import os
import asyncio
import hashlib
import edge_tts
import subprocess
import logging
import traceback
from datetime import datetime

logger = logging.getLogger("tts")

class TTSManager:
    def __init__(self, cache_dir="tts_cache"):
        """文本转语音管理器"""
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 用于跟踪从缓存加载的文件
        self.cache_hits = set()
        # 用于跟踪新生成的文件
        self.newly_generated = set()
        # 用于跟踪最近生成/使用的文件及其状态
        self.recent_files = {}
        
    def get_cache_path(self, text, voice="zh-CN-XiaoxiaoNeural"):
        """获取缓存文件路径"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{text_hash}_{voice}.wav")
        
    def is_from_cache(self, text, voice="zh-CN-XiaoxiaoNeural"):
        """检查是否从缓存加载"""
        cache_path = self.get_cache_path(text, voice)
        # 如果路径在缓存命中集合中，或者不在新生成集合中但文件存在
        return (cache_path in self.cache_hits) or (cache_path not in self.newly_generated and os.path.exists(cache_path))
            
    async def generate_tts(self, text, voice="zh-CN-XiaoxiaoNeural"):
        """使用edge-tts直接生成WAV语音文件"""
        try:
            # 获取缓存文件路径
            wav_path = self.get_cache_path(text, voice)
            
            # 如果已经生成过，直接返回
            if os.path.exists(wav_path):
                # 记录缓存命中
                self.cache_hits.add(wav_path)
                # 更新最近文件记录
                self.recent_files[wav_path] = {
                    'text': text,
                    'voice': voice,
                    'from_cache': True,
                    'time': datetime.now()
                }
                return wav_path
                
            # 创建临时文件路径
            temp_audio = os.path.join(self.cache_dir, f"{os.path.basename(wav_path)}_temp.mp3")
            
            # 生成语音
            logger.info(f"正在生成语音: '{text[:30]}...'")
            communicate = edge_tts.Communicate(text, voice)
            
            # 直接生成WAV格式音频
            try:
                # 首先使用edge-tts保存为默认格式
                await communicate.save(temp_audio)
                
                # 使用ffmpeg直接转换为16000Hz，单声道，16位PCM的WAV格式
                cmd = [
                    'ffmpeg', '-y', 
                    '-i', temp_audio, 
                    '-acodec', 'pcm_s16le', 
                    '-ar', '16000', 
                    '-ac', '1', 
                    wav_path
                ]
                
                process = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # 删除临时文件
                try:
                    if os.path.exists(temp_audio):
                        os.remove(temp_audio)
                except Exception as e:
                    logger.warning(f"无法删除临时文件: {e}")
                
                logger.info(f"语音生成成功: {os.path.basename(wav_path)}")
                
                # 记录新生成的文件
                self.newly_generated.add(wav_path)
                # 更新最近文件记录
                self.recent_files[wav_path] = {
                    'text': text,
                    'voice': voice,
                    'from_cache': False,
                    'time': datetime.now()
                }
            except Exception as e:
                logger.error(f"语音生成失败: {e}")
                logger.error(f"详细错误: {traceback.format_exc()}")
                return None
            
            return wav_path
        except Exception as e:
            logger.error(f"TTS生成失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
            
    def generate_tts_sync(self, text, voice="zh-CN-XiaoxiaoNeural"):
        """同步版本的TTS生成函数"""
        try:
            return asyncio.run(self.generate_tts(text, voice))
        except Exception as e:
            logger.error(f"同步TTS生成失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
            
    def get_cache_statistics(self):
        """获取缓存统计信息"""
        stats = {
            'total_files': 0,
            'cache_hits': len(self.cache_hits),
            'newly_generated': len(self.newly_generated),
            'cache_size_bytes': 0
        }
        
        # 计算缓存总大小和文件数量
        if os.path.exists(self.cache_dir):
            for file in os.listdir(self.cache_dir):
                if file.endswith('.wav'):
                    file_path = os.path.join(self.cache_dir, file)
                    stats['total_files'] += 1
                    stats['cache_size_bytes'] += os.path.getsize(file_path)
        
        return stats 