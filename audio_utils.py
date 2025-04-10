import os
import wave
import logging
import subprocess
import tempfile

logger = logging.getLogger("audio_utils")

class AudioUtils:
    """音频处理工具类，专门处理WAV文件"""
    
    @staticmethod
    def ensure_sip_compatible_format(input_file, output_file=None, sample_rate=8000, channels=1):
        """确保WAV文件为SIP兼容格式
        
        Args:
            input_file: 输入文件路径（必须是WAV格式）
            output_file: 输出文件路径，如果为None则在原文件旁创建临时文件
            sample_rate: 目标采样率，默认为8000Hz (SIP标准)
            channels: 目标声道数，默认为1 (单声道)
            
        Returns:
            str: 处理后的文件路径，如失败则返回None
        """
        try:
            # 检查输入文件是否存在
            if not os.path.exists(input_file):
                logger.error(f"输入文件不存在: {input_file}")
                return None
                
            # 检查文件扩展名，拒绝非WAV文件
            if not input_file.lower().endswith('.wav'):
                logger.error(f"只支持WAV格式文件，当前文件: {input_file}")
                return None
                
            # 分析现有WAV文件
            try:
                with wave.open(input_file, 'rb') as wf:
                    orig_channels = wf.getnchannels()
                    orig_sampwidth = wf.getsampwidth()
                    orig_framerate = wf.getframerate()
                    
                    # 检查是否已经是目标格式
                    if orig_channels == channels and orig_framerate == sample_rate and orig_sampwidth == 2:
                        logger.info(f"文件已经是兼容格式: {input_file}")
                        return input_file
                        
                    logger.info(f"需要转换WAV文件: {input_file}")
            except Exception as e:
                logger.error(f"分析WAV文件时出错: {e}")
                return None
                
            # 如果未指定输出文件，创建临时文件
            if not output_file:
                dir_name = os.path.dirname(input_file)
                base_name = os.path.basename(input_file)
                name, _ = os.path.splitext(base_name)
                output_file = os.path.join(dir_name, f"{name}_converted.wav")
                
            # 使用ffmpeg转换
            cmd = [
                'ffmpeg', '-y', 
                '-i', input_file, 
                '-acodec', 'pcm_s16le',  # 16位PCM编码
                '-ar', str(sample_rate),  # 采样率
                '-ac', str(channels),     # 声道数
                output_file
            ]
            
            # 执行转换
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"转换失败: {result.stderr}")
                return None
                
            logger.info(f"WAV文件已转换为兼容格式: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"确保SIP兼容格式过程中出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None 