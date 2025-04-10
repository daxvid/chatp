import os
import logging
import subprocess

logger = logging.getLogger("audio")

class AudioUtils:
    """音频文件处理工具类"""
    
    @staticmethod
    def convert_to_sip_compatible_wav(wav_file, temp_file=None, sample_rate=8000, channels=1):
        """转换WAV文件为PJSIP兼容格式（单声道、16位、指定采样率）
        
        Args:
            wav_file: 输入WAV文件路径
            temp_file: 临时文件路径，如果为None则自动生成
            sample_rate: 采样率，默认8000Hz (适合SIP)
            channels: 声道数，默认1 (单声道)
            
        Returns:
            转换是否成功
        """
        try:
            # 如果未指定临时文件，自动生成
            if not temp_file:
                temp_file = wav_file + '.temp.wav'
            
            # 使用ffmpeg转换
            cmd = [
                'ffmpeg', '-y', 
                '-i', wav_file, 
                '-acodec', 'pcm_s16le', 
                '-ar', str(sample_rate), 
                '-ac', str(channels), 
                temp_file
            ]
            
            logger.info(f"转换WAV为兼容格式: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            
            # 替换原始文件
            os.rename(temp_file, wav_file)
            logger.info(f"WAV文件已转换为兼容格式: {wav_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"WAV格式转换失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False
    
    @staticmethod
    def ensure_sip_compatible_format(audio_file, output_file=None, sample_rate=8000, channels=1):
        """确保音频文件为SIP兼容格式
        
        检查WAV文件格式并进行必要转换，确保其为SIP兼容格式
        (单声道、16位、8kHz采样率)
        
        Args:
            audio_file: 输入音频文件路径
            output_file: 输出文件路径，如果为None则覆盖原文件
            sample_rate: 采样率，默认8000Hz
            channels: 声道数，默认1 (单声道)
            
        Returns:
            转换后的文件路径（成功）或None（失败）
        """
        try:
            if not os.path.exists(audio_file):
                logger.error(f"音频文件不存在: {audio_file}")
                return None
            
            # 检查文件是否为WAV格式
            _, ext = os.path.splitext(audio_file)
            if ext.lower() != '.wav':
                logger.error(f"不支持的音频格式: {ext}，仅支持WAV格式")
                return None
            
            # 如果未指定输出文件，使用原文件
            if not output_file:
                output_file = audio_file
            
            # 检查WAV格式是否符合SIP要求
            try:
                import wave
                with wave.open(audio_file, 'rb') as wf:
                    if wf.getnchannels() != channels or wf.getsampwidth() != 2 or wf.getframerate() != sample_rate:
                        logger.warning(f"音频文件不是指定格式(单声道、16位、{sample_rate}Hz采样率): {audio_file}")
                        
                        # 需要转换格式
                        temp_file = output_file + '.temp.wav'
                        cmd = [
                            'ffmpeg', '-y', 
                            '-i', audio_file, 
                            '-acodec', 'pcm_s16le', 
                            '-ar', str(sample_rate), 
                            '-ac', str(channels), 
                            temp_file
                        ]
                        
                        logger.info(f"转换WAV为兼容格式: {' '.join(cmd)}")
                        subprocess.run(cmd, check=True)
                        
                        # 如果输出文件不是原文件，直接重命名；否则使用替换
                        if output_file != audio_file:
                            os.rename(temp_file, output_file)
                        else:
                            os.remove(audio_file)
                            os.rename(temp_file, output_file)
                        
                        logger.info(f"WAV文件已转换为兼容格式: {output_file}")
            except Exception as e:
                logger.error(f"检查WAV格式时出错: {e}")
                return None
                
            return output_file
            
        except Exception as e:
            logger.error(f"处理音频文件失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
    
    @staticmethod
    def enhance_audio_volume(audio_file, volume=1.5):
        """增强音频音量
        
        Args:
            audio_file: 输入音频文件路径
            volume: 音量倍数，默认1.5
            
        Returns:
            处理后的音频文件路径
        """
        try:
            # 生成输出文件名
            output_file = f"{os.path.splitext(audio_file)[0]}_vol{volume}.wav"
            
            # 使用ffmpeg增加音量
            cmd = [
                'ffmpeg', '-y', 
                '-i', audio_file, 
                '-af', f'volume={volume}',  # 增加音量
                '-acodec', 'pcm_s16le', 
                output_file
            ]
            
            logger.info(f"增强音频音量: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            
            if os.path.exists(output_file):
                logger.info(f"音频音量增强成功: {output_file}")
                return output_file
            else:
                logger.error(f"音频音量增强失败，输出文件不存在")
                return audio_file
                
        except Exception as e:
            logger.error(f"增强音频音量失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return audio_file 