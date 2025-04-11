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
        """使用edge-tts直接生成WAV语音文件"""
        try:
            # 创建文件名（使用文本的哈希值）
            text_hash = hashlib.md5(text.encode()).hexdigest()
            wav_path = os.path.join(self.cache_dir, f"{text_hash}_{voice}.wav")
            
            # 如果已经生成过，直接返回
            if os.path.exists(wav_path):
                logger.info(f"使用缓存的TTS文件: {wav_path}")
                return wav_path
                
            # 创建临时PCM文件
            pcm_path = os.path.join(self.cache_dir, f"{text_hash}_{voice}_temp.pcm")
            
            # 生成语音
            logger.info(f"正在使用edge-tts生成语音: '{text}'")
            communicate = edge_tts.Communicate(text, voice)
            
            # 直接生成WAV格式音频
            try:
                # 首先使用edge-tts保存为默认格式
                temp_audio = os.path.join(self.cache_dir, f"{text_hash}_{voice}_temp.mp3")
                await communicate.save(temp_audio)
                
                # 使用ffmpeg直接转换为8000Hz，单声道，16位PCM的WAV格式
                cmd = [
                    'ffmpeg', '-y', 
                    '-i', temp_audio, 
                    '-acodec', 'pcm_s16le', 
                    '-ar', '8000', 
                    '-ac', '1', 
                    wav_path
                ]
                
                logger.info(f"直接转换为WAV格式: {' '.join(cmd)}")
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # 删除临时文件
                try:
                    if os.path.exists(temp_audio):
                        os.remove(temp_audio)
                    if os.path.exists(pcm_path):
                        os.remove(pcm_path)
                except Exception as e:
                    logger.warning(f"无法删除临时文件: {e}")
                
                logger.info(f"WAV格式生成成功: {wav_path}")
            except Exception as e:
                logger.error(f"WAV格式生成失败: {e}")
                logger.error(f"详细错误: {traceback.format_exc()}")
                return None
            
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