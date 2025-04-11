import os
import time
import logging
import shutil
import threading
import subprocess
import traceback

# 尝试导入常用音频处理库
HAVE_SOUNDFILE = False
HAVE_NUMPY = False
HAVE_SCIPY = False

try:
    import soundfile as sf
    HAVE_SOUNDFILE = True
except ImportError:
    pass

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    pass

try:
    from scipy import signal
    HAVE_SCIPY = True
except ImportError:
    pass

logger = logging.getLogger("sip")

class WhisperTranscriber:
    """Whisper语音转文本处理类"""
    
    def __init__(self, whisper_model=None):
        self.whisper_model = whisper_model
        self.transcriber_active = False
        self.transcriber_thread = None
        self.recording_file = None
        self.response_callback = None
        self.play_response_callback = None
    
    def set_model(self, model):
        """设置Whisper模型"""
        self.whisper_model = model
    
    def transcribe_file(self, audio_file):
        """转录单个音频文件"""
        try:
            if not self.whisper_model:
                logger.error("Whisper模型未加载，无法进行语音识别")
                return None
                
            if audio_file and os.path.exists(audio_file):
                logger.info(f"开始转录音频: {audio_file}")
                # 检查文件大小，确保不是空文件
                if os.path.getsize(audio_file) < 1000:  # 小于1KB的文件可能有问题
                    logger.warning(f"录音文件过小，可能没有录到声音: {audio_file}")
                    return None
                
                try:
                    # 确保处理前没有其他程序占用文件
                    temp_file = audio_file + ".temp"
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                    
                    # 复制一份文件进行处理，避免文件锁定问题
                    shutil.copy2(audio_file, temp_file)
                    
                    # 使用更安全的方式调用whisper transcribe
                    try:
                        result = self.whisper_model.transcribe(
                            temp_file,
                            language="zh",
                            task="transcribe",
                            verbose=False
                        )
                        
                        # 清理临时文件
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                            
                        if isinstance(result, dict) and 'text' in result:
                            logger.info(f"语音识别结果: {result['text']}")
                            return result['text']
                        else:
                            logger.warning(f"语音识别结果格式异常: {type(result)}")
                            if isinstance(result, dict):
                                logger.warning(f"可用键: {result.keys()}")
                            return str(result) if result else None
                    except Exception as e:
                        logger.warning(f"Whisper处理失败:{temp_file} {e}")
                except Exception as e:
                    logger.error(f"语音识别处理失败: {e}")
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    return None
            else:
                logger.warning(f"录音文件不存在: {audio_file}")
            return None
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None
    
    def start_realtime_transcription(self, recording_file, response_callback=None, play_response_callback=None):
        """存储实时转录参数但不启动线程（兼容性方法）
        
        Args:
            recording_file (str): 录音文件路径
            response_callback (callable): 转录结果回调函数
            play_response_callback (callable): 播放响应回调函数
        """
        try:
            self.recording_file = recording_file
            self.response_callback = response_callback
            self.play_response_callback = play_response_callback
            
            # 不再创建线程，而是只保存参数供main.py中的主循环使用
            self.transcriber_active = True
            logger.info("实时转录参数已保存（兼容性模式，实际转录在main.py中执行）")
            return True
        except Exception as e:
            logger.error(f"保存实时转录参数失败: {e}")
            return False
    
    def stop_transcription(self):
        """停止实时转录"""
        if self.transcriber_active:
            self.transcriber_active = False
            logger.info("实时语音转录已停止")
    
    # 不再需要_realtime_transcription_loop方法，已将其功能集成到main.py的主循环中
    
    def _transcribe_segment(self, processed_file, segment_count):
        """转录单个音频段，含重试逻辑"""
        if not self.whisper_model:
            logger.warning("Whisper模型未加载，无法进行语音识别")
            return None
            
        max_retries = 3
        retry_count = 0
        segment_dir = os.path.dirname(processed_file)
        
        while retry_count < max_retries:
            try:
                # 使用原始方法直接转录文件
                logger.info(f"尝试转录音频段 {segment_count} (尝试 {retry_count+1}/{max_retries})")
                result = self.whisper_model.transcribe(
                    processed_file,
                    language="zh",
                    fp16=False
                )
                text = result.get("text", "").strip()
                
                if text:
                    logger.info(f"语音识别结果 (段{segment_count}): {text}")
                    return text
                else:
                    logger.info(f"语音识别结果为空 (段{segment_count})")
                    
                # 成功则跳出重试循环
                break
                
            except Exception as e:
                retry_count += 1
                logger.error(f"转录尝试 {retry_count}/{max_retries} 失败: {e}")
                logger.error(f"详细错误: {traceback.format_exc()}")
                
                # 尝试使用复制的文件
                if retry_count < max_retries:
                    try:
                        # 重新复制一个文件尝试
                        retry_file = os.path.join(segment_dir, f"retry_{segment_count}_{retry_count}.wav")
                        shutil.copy2(processed_file, retry_file)
                        logger.info(f"尝试使用新复制的文件: {retry_file}")
                        
                        result = self.whisper_model.transcribe(
                            retry_file,
                            language="zh",
                            fp16=False
                        )
                        text = result.get("text", "").strip()
                        
                        if text:
                            logger.info(f"语音识别结果 (段{segment_count}-重试): {text}")
                            
                            # 清理临时文件
                            try:
                                os.remove(retry_file)
                            except:
                                pass
                                
                            # 成功返回结果
                            return text
                    except Exception as er:
                        logger.error(f"重试文件处理失败: {er}")
                
                if retry_count >= max_retries:
                    logger.error(f"转录段 {segment_count} 失败，已达最大尝试次数")
                    # 尝试使用替代方法
                    try:
                        logger.info(f"尝试使用替代方法转录...")
                        
                        # 尝试使用系统命令转录（如果安装了whisper命令行工具）
                        try:
                            cmd = [
                                "whisper", processed_file,
                                "--language", "zh",
                                "--model", "small",
                                "--output_format", "txt",
                                "--output_dir", segment_dir
                            ]
                            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                            output_file = os.path.join(segment_dir, f"processed_{segment_count}.txt")
                            
                            if os.path.exists(output_file):
                                with open(output_file, 'r', encoding='utf-8') as f:
                                    text = f.read().strip()
                                    if text:
                                        logger.info(f"替代方法语音识别结果 (段{segment_count}): {text}")
                                        return text
                        except Exception as e3:
                            logger.error(f"替代转录方法也失败: {e3}")
                    except Exception as e2:
                        logger.error(f"尝试替代方法失败: {e2}")
                
                # 等待一会再重试
                time.sleep(1)
        
        return None 