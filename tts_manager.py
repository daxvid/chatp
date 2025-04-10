import os
import asyncio
import hashlib
import edge_tts
import subprocess
import logging

# 引入AudioUtils类
from audio_utils import AudioUtils

logger = logging.getLogger("tts")

class TTSManager:
    def __init__(self, cache_dir="tts_cache"):
        """文本转语音管理器"""
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        
    async def generate_tts(self, text, voice="zh-CN-XiaoxiaoNeural"):
        """使用edge-tts生成语音文件"""
        try:
            # 创建文件名（使用文本的哈希值）
            text_hash = hashlib.md5(text.encode()).hexdigest()
            mp3_path = os.path.join(self.cache_dir, f"{text_hash}_{voice}.mp3")
            wav_path = os.path.join(self.cache_dir, f"{text_hash}_{voice}.wav")
            
            # 如果已经生成过，直接返回
            if os.path.exists(wav_path):
                logger.info(f"使用缓存的TTS文件: {wav_path}")
                return wav_path
                
            # 生成语音
            logger.info(f"正在使用edge-tts生成语音: '{text}'")
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(mp3_path)
            logger.info(f"TTS生成成功: {mp3_path}")
            
            # 转换为WAV格式 - 使用AudioUtils
            converted_wav = AudioUtils.convert_mp3_to_wav(mp3_path, wav_path, 8000, 1)
            if not converted_wav:
                logger.error(f"无法转换TTS MP3文件为WAV格式")
                return mp3_path
            
            return wav_path
        except Exception as e:
            logger.error(f"TTS生成失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
    
    def generate_tts_sync(self, text, voice="zh-CN-XiaoxiaoNeural"):
        """同步版本的TTS生成函数"""
        try:
            return asyncio.run(self.generate_tts(text, voice))
        except Exception as e:
            logger.error(f"同步TTS生成失败: {e}")
            return None 