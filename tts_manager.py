import os
import asyncio
import hashlib
import edge_tts
import subprocess
import logging

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
            
            # 转换为WAV格式
            self._convert_mp3_to_wav(mp3_path, wav_path)
            
            return wav_path
        except Exception as e:
            logger.error(f"TTS生成失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
            
    def _convert_mp3_to_wav(self, mp3_file, wav_file):
        """将MP3文件转换为PJSIP兼容的WAV格式"""
        try:
            # 使用ffmpeg转换
            cmd = [
                'ffmpeg', '-y', 
                '-i', mp3_file, 
                '-acodec', 'pcm_s16le', 
                '-ar', '8000', 
                '-ac', '1', 
                wav_file
            ]
            
            logger.info(f"转换MP3到WAV: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            logger.info(f"MP3成功转换为WAV: {wav_file}")
            
        except Exception as e:
            logger.error(f"MP3转换失败: {e}")
            raise
    
    def generate_tts_sync(self, text, voice="zh-CN-XiaoxiaoNeural"):
        """同步版本的TTS生成函数"""
        try:
            return asyncio.run(self.generate_tts(text, voice))
        except Exception as e:
            logger.error(f"同步TTS生成失败: {e}")
            return None 