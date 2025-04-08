import os
import re
import ssl
import time
import yaml
import socket
import logging
import pjsua2 as pj
import threading
import shutil
import math
import struct
import random
import wave
from datetime import datetime

# 禁用SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

logger = logging.getLogger("sip")

class SIPCall(pj.Call):
    """SIP通话类，继承自pjsua2.Call"""
    def __init__(self, acc, voice_file=None, whisper_model=None, phone_number=None, response_voice_file=None):
        pj.Call.__init__(self, acc)
        self.voice_file = voice_file
        self.response_voice_file = response_voice_file
        self.voice_data = None
        self.recorder = None
        self.recording_file = None
        self.whisper_model = whisper_model
        self.phone_number = phone_number
        self.audio_port = None
        self.has_played_response = False
        
        if self.voice_file:
            self._load_voice_file()
        if self.response_voice_file:
            self._load_response_file()

    def _load_voice_file(self):
        """加载语音文件"""
        try:
            # 检查文件扩展名
            if self.voice_file.lower().endswith('.mp3'):
                logger.info(f"检测到MP3文件: {self.voice_file}")
                # MP3文件需要转换为WAV格式
                self._convert_mp3_to_wav()
                # 转换后的文件路径
                self.voice_file = self.voice_file.rsplit('.', 1)[0] + '.wav'
                
            with wave.open(self.voice_file, 'rb') as wf:
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 8000:
                    logger.warning("语音文件不是单声道、16位、8kHz采样率，尝试转换...")
                    self._convert_to_compatible_wav()
                self.voice_data = wf.readframes(wf.getnframes())
                logger.info(f"语音文件加载成功: {self.voice_file}")
        except Exception as e:
            logger.error(f"加载语音文件失败: {e}")
            self.voice_data = None
            
    def _convert_mp3_to_wav(self):
        """将MP3文件转换为WAV格式"""
        try:
            import subprocess
            output_wav = self.voice_file.rsplit('.', 1)[0] + '.wav'
            
            # 使用ffmpeg转换
            cmd = [
                'ffmpeg', '-y', 
                '-i', self.voice_file, 
                '-acodec', 'pcm_s16le', 
                '-ar', '8000', 
                '-ac', '1', 
                output_wav
            ]
            
            logger.info(f"转换MP3到WAV: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            logger.info(f"MP3成功转换为WAV: {output_wav}")
            
        except Exception as e:
            logger.error(f"MP3转换失败: {e}")
            raise
            
    def _convert_to_compatible_wav(self):
        """转换WAV文件为PJSIP兼容格式（单声道、16位、8kHz采样率）"""
        try:
            import subprocess
            temp_file = self.voice_file + '.temp.wav'
            
            # 使用ffmpeg转换
            cmd = [
                'ffmpeg', '-y', 
                '-i', self.voice_file, 
                '-acodec', 'pcm_s16le', 
                '-ar', '8000', 
                '-ac', '1', 
                temp_file
            ]
            
            logger.info(f"转换WAV为兼容格式: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            
            # 替换原始文件
            import os
            os.rename(temp_file, self.voice_file)
            logger.info(f"WAV文件已转换为兼容格式: {self.voice_file}")
            
        except Exception as e:
            logger.error(f"WAV格式转换失败: {e}")
            raise

    def _load_response_file(self):
        """加载响应语音文件"""
        try:
            # 检查文件扩展名
            if self.response_voice_file.lower().endswith('.mp3'):
                logger.info(f"检测到MP3响应文件: {self.response_voice_file}")
                # MP3文件需要转换为WAV格式
                self._convert_mp3_to_wav(self.response_voice_file)
                # 转换后的文件路径
                self.response_voice_file = self.response_voice_file.rsplit('.', 1)[0] + '.wav'
                
            with wave.open(self.response_voice_file, 'rb') as wf:
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 8000:
                    logger.warning("响应语音文件不是单声道、16位、8kHz采样率，尝试转换...")
                    self._convert_to_compatible_wav(self.response_voice_file)
                logger.info(f"响应语音文件加载成功: {self.response_voice_file}")
        except Exception as e:
            logger.error(f"加载响应语音文件失败: {e}")

    def start_recording(self, phone_number):
        """开始录音"""
        try:
            # 创建recordings目录
            recordings_dir = "recordings"
            os.makedirs(recordings_dir, exist_ok=True)
            
            # 清理电话号码中的特殊字符，只保留数字
            clean_number = ''.join(filter(str.isdigit, phone_number))
            
            # 创建录音文件名，格式：电话号码_日期时间.wav
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{clean_number}_{timestamp}.wav"
            self.recording_file = os.path.join(recordings_dir, filename)
            
            # 创建录音器
            self.recorder = pj.AudioMediaRecorder()
            self.recorder.createRecorder(self.recording_file)
            
            # 连接到通话 - 恢复到之前的录音方式
            try:
                # 首先尝试使用getAudioMedia方法
                call_media = self.getAudioMedia(-1)  # -1表示第一个可用的音频媒体
                logger.info(f"成功获取音频媒体")
            except Exception as e:
                logger.error(f"无法获取音频媒体: {e}")
                logger.error("录音功能不可用")
                return False
                
            # 开始录音
            call_media.startTransmit(self.recorder)
            
            logger.info(f"开始录音: {self.recording_file}")
            return True
            
        except Exception as e:
            logger.error(f"录音启动失败: {e}")
            self.recording_file = None
            return False
    
    def stop_recording(self):
        """停止录音"""
        try:
            if self.recorder:
                # 停止录音
                self.recorder = None
                logger.info(f"录音已停止: {self.recording_file}")
                return True
            return False
        except Exception as e:
            logger.error(f"停止录音失败: {e}")
            return False
    
    def transcribe_audio(self):
        """使用Whisper转录音频"""
        try:
            if not self.whisper_model:
                logger.error("Whisper模型未加载，无法进行语音识别")
                return None
                
            if self.recording_file and os.path.exists(self.recording_file):
                logger.info(f"开始转录音频: {self.recording_file}")
                # 检查文件大小，确保不是空文件
                if os.path.getsize(self.recording_file) < 1000:  # 小于1KB的文件可能有问题
                    logger.warning(f"录音文件过小，可能没有录到声音: {self.recording_file}")
                
                try:
                    result = self.whisper_model.transcribe(self.recording_file)
                    logger.info(f"语音识别结果: {result['text']}")
                    return result['text']
                except Exception as e:
                    logger.error(f"语音识别处理失败: {e}")
                    return None
            else:
                logger.warning(f"录音文件不存在: {self.recording_file}")
            return None
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            return None
    
    def play_response_after_speech(self):
        """在对方说完话后播放响应语音"""
        if self.has_played_response:
            logger.info("已经播放过响应，不再重复播放")
            return
            
        try:
            logger.info("准备播放响应语音")
            # 等待一小段时间，确保对方说完
            time.sleep(0.5)
            
            if not self.response_voice_file or not os.path.exists(self.response_voice_file):
                logger.warning(f"响应语音文件不存在或未指定: {self.response_voice_file}")
                return
                
            # 创建音频播放器
            player = pj.AudioMediaPlayer()
            logger.info(f"尝试播放响应语音文件: {self.response_voice_file}")
            
            # 加载并检查语音文件
            try:
                player.createPlayer(self.response_voice_file)
                logger.info("响应语音播放器已创建")
            except Exception as e:
                logger.error(f"创建响应播放器失败: {e}")
                return
                
            # 获取通话媒体
            try:
                audio_stream = self.getAudioMedia(-1)
                logger.info("成功获取音频媒体")
            except Exception as e:
                logger.error(f"获取音频媒体失败: {e}")
                logger.error("响应语音播放功能不可用")
                return
            
            # 开始传输音频
            player.startTransmit(audio_stream)
            logger.info("开始播放响应语音，音频传输已启动")
            self.has_played_response = True
            
        except Exception as e:
            logger.error(f"播放响应语音过程中出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
    
    def onCallMediaState(self, prm):
        """媒体状态改变时的回调函数"""
        logger.info("媒体状态已改变")
        try:
            # 检查是否有音频媒体
            try:
                # 获取远程音频媒体
                audio_media = self.getAudioMedia(-1)
                logger.info("成功获取音频媒体")
                
                # 如果已经创建了音频端口，连接它用于实时转录
                if hasattr(self, 'audio_port') and self.audio_port:
                    logger.info("连接音频媒体到转录端口")
                    audio_media.startTransmit(self.audio_port)
                    logger.info("音频媒体已连接到转录端口")
                
                # 不在这里处理录音，已经在start_recording中处理了
                
            except Exception as e:
                logger.error(f"处理音频媒体时出错: {e}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
                
        except Exception as e:
            logger.error(f"处理媒体状态变化时出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")

    def onCallState(self, prm):
        """呼叫状态改变时的回调函数"""
        try:
            ci = self.getInfo()
            state_names = {
                pj.PJSIP_INV_STATE_NULL: "NULL",
                pj.PJSIP_INV_STATE_CALLING: "CALLING",
                pj.PJSIP_INV_STATE_INCOMING: "INCOMING",
                pj.PJSIP_INV_STATE_EARLY: "EARLY",
                pj.PJSIP_INV_STATE_CONNECTING: "CONNECTING",
                pj.PJSIP_INV_STATE_CONFIRMED: "CONFIRMED",
                pj.PJSIP_INV_STATE_DISCONNECTED: "DISCONNECTED"
            }
            state_name = state_names.get(ci.state, f"未知状态({ci.state})")
            logger.info(f"呼叫状态改变: {state_name}, 状态码: {ci.lastStatusCode}, 原因: {ci.lastReason}")
            
            # 根据不同的状态执行不同的操作
            if ci.state == pj.PJSIP_INV_STATE_CALLING:
                logger.info("正在呼叫中...")
                
            elif ci.state == pj.PJSIP_INV_STATE_EARLY:
                logger.info("对方电话开始响铃...")
                
            elif ci.state == pj.PJSIP_INV_STATE_CONNECTING:
                logger.info("正在建立连接...")
                
            elif ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
                logger.info("通话已接通")
                
                # 等待确保通话流建立
                time.sleep(0.5)
                
                # 开始录音
                if prm and hasattr(prm, 'remoteUri') and prm.remoteUri:
                    self.start_recording(prm.remoteUri)
                elif self.phone_number:
                    logger.info(f"使用预设电话号码进行录音: {self.phone_number}")
                    self.start_recording(self.phone_number)
                else:
                    logger.warning("缺少远程URI信息和预设号码，使用未知号码录音")
                    self.start_recording("unknown")
                
                # 获取Endpoint实例，方便后续使用
                if hasattr(self.acc, "_pjsip_endpoint") and self.acc._pjsip_endpoint:
                    self.ep = self.acc._pjsip_endpoint
                else:
                    # 尝试获取全局实例
                    self.ep = pj.Endpoint.instance()
                
                # 启动实时语音转录
                if self.whisper_model:
                    logger.info("初始化实时语音转录...")
                    try:
                        # 创建音频媒体端口并传入当前call对象
                        self.audio_port = MyAudioMediaPort(self.whisper_model, self)
                        # 启动实时转录
                        if self.audio_port.start_realtime_transcription(self):
                            logger.info("实时语音转录已启动")
                        else:
                            logger.error("启动实时语音转录失败")
                    except Exception as e:
                        logger.error(f"初始化实时语音转录时出错: {e}")
                        import traceback
                        logger.error(f"详细错误: {traceback.format_exc()}")
                else:
                    logger.warning("Whisper模型未设置，无法进行实时语音转录")
                    
            elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                if ci.lastStatusCode >= 400:
                    logger.error(f"通话失败: 状态码={ci.lastStatusCode}, 原因={ci.lastReason}")
                else:
                    logger.info(f"通话已结束: 状态码={ci.lastStatusCode}, 原因={ci.lastReason}")
                
                # 停止实时转录
                try:
                    if hasattr(self, 'audio_port') and self.audio_port:
                        # 在主线程中安全断开连接
                        try:
                            # 获取音频媒体对象
                            audio_media = self.getAudioMedia(-1)
                            # 停止传输
                            if audio_media:
                                audio_media.stopTransmit(self.audio_port)
                                logger.info("音频媒体传输已停止")
                        except Exception as e:
                            logger.error(f"停止音频传输时出错: {e}")
                            
                        # 停止转录线程
                        self.audio_port.transcription_active = False
                        logger.info("实时语音转录已停止")
                except Exception as e:
                    logger.error(f"停止实时语音转录时出错: {e}")
                
                # 停止录音
                self.stop_recording()
                # 转录音频 - 这里仍然保留整个通话的录音转录功能
                if self.recording_file and os.path.exists(self.recording_file):
                    self.transcribe_audio()
        except Exception as e:
            logger.error(f"处理呼叫状态变化时出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")


class SIPCaller:
    """SIP呼叫管理类"""
    def __init__(self, sip_config):
        self.config = sip_config
        self.ep = None
        self.acc = None
        self.current_call = None
        self.phone_number = None
        self.whisper_model = None
        
        # 初始化PJSIP
        self._init_pjsua2()

    def _init_pjsua2(self):
        """初始化PJSIP"""
        try:
            # 创建Endpoint
            self.ep = pj.Endpoint()
            self.ep.libCreate()

            # 初始化库
            ep_cfg = pj.EpConfig()
            # 禁用SSL证书验证
            ep_cfg.uaConfig.verifyServerCert = False
            
            # 设置日志级别
            ep_cfg.logConfig.level = 5  # 设置为高级别日志，便于调试
            ep_cfg.logConfig.consoleLevel = 5
            
            # 初始化媒体配置
            ep_cfg.medConfig.ecTailLen = 0  # 禁用回声消除
            
            # 初始化PJSIP库
            logger.info("正在初始化PJSIP库...")
            self.ep.libInit(ep_cfg)
            logger.info("PJSIP库初始化成功")

            # 创建传输
            sipTpConfig = pj.TransportConfig()
            if self.config.get('bind_port'):
                sipTpConfig.port = self.config.get('bind_port', 5060)
            else:
                sipTpConfig.port = random.randint(6000, 8000)
            
            # 指定本地IP（如果配置中有）
            if self.config.get('bind_ip'):
                sipTpConfig.boundAddr = self.config.get('bind_ip')
                logger.info(f"绑定本地IP: {sipTpConfig.boundAddr}:{sipTpConfig.port}")
            
            logger.info(f"创建SIP传输，端口: {sipTpConfig.port}")
            self.transport_id = self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, sipTpConfig)
            logger.info(f"SIP传输创建成功，ID: {self.transport_id}")
            # transportCreate返回的是整数ID，不是对象，无法直接调用getInfo()
            # 记录一下基本信息即可
            logger.info(f"本地SIP端口: {sipTpConfig.port}")

            # 启动库
            logger.info("启动PJSIP库...")
            self.ep.libStart()
            logger.info("PJSIP库启动成功")

            # 创建账户配置
            acc_cfg = pj.AccountConfig()
            acc_cfg.idUri = f"sip:{self.config['username']}@{self.config['server']}:{self.config['port']}"
            acc_cfg.regConfig.registrarUri = f"sip:{self.config['server']}:{self.config['port']}"
            
            # 配置认证信息
            cred_info = pj.AuthCredInfo(
                "digest",
                "*",
                self.config['username'],
                0,
                self.config['password']
            )
            acc_cfg.sipConfig.authCreds.append(cred_info)
            
            # 设置注册超时时间
            if self.config.get('register_refresh'):
                acc_cfg.regConfig.timeoutSec = int(self.config.get('register_refresh'))
                logger.info(f"设置注册刷新时间: {acc_cfg.regConfig.timeoutSec}秒")
            
            # 设置Keep-Alive时间 - 注释掉这部分，因为在Python绑定中不存在这个属性
            # if self.config.get('keep_alive'):
            #     acc_cfg.sipConfig.keepAliveIntervalSec = int(self.config.get('keep_alive'))
            #     logger.info(f"设置Keep-Alive时间: {acc_cfg.sipConfig.keepAliveIntervalSec}秒")
            
            logger.info(f"创建SIP账户: {acc_cfg.idUri}, 注册到: {acc_cfg.regConfig.registrarUri}")

            # 创建账户
            self.acc = pj.Account()
            self.acc.create(acc_cfg)
            
            # 等待注册完成
            logger.info("等待SIP注册...")
            timeout = 30  # 30秒超时
            start_time = time.time()
            
            # 修复部分：确保self.acc是有效的Account对象，并且可以调用getInfo()
            # 同时处理可能的异常情况
            while time.time() - start_time < timeout:
                try:
                    if not isinstance(self.acc, pj.Account):
                        logger.error(f"账户对象类型错误: {type(self.acc)}")
                        break
                        
                    acc_info = self.acc.getInfo()
                    if acc_info.regStatus == pj.PJSIP_SC_OK:
                        logger.info("SIP注册成功")
                        break
                    elif acc_info.regStatus >= 300:  # 任何错误状态码
                        logger.error(f"SIP注册失败，状态码: {acc_info.regStatus}")
                        break
                except Exception as e:
                    logger.error(f"获取账户信息时出错: {e}")
                    break
                    
                time.sleep(0.5)  # 稍微增加检查间隔，减少CPU使用
            
            # 再次检查注册状态
            try:
                if isinstance(self.acc, pj.Account):
                    acc_info = self.acc.getInfo()
                    logger.info(f"SIP账户信息: URI={acc_info.uri}, 状态码={acc_info.regStatus}, 过期={acc_info.regExpiresSec}秒")
                    
                    if acc_info.regStatus != pj.PJSIP_SC_OK:
                        logger.warning(f"SIP注册未成功完成，状态码: {acc_info.regStatus}")
                else:
                    logger.error("账户对象无效")
            except Exception as e:
                logger.error(f"获取最终账户状态时出错: {e}")

            logger.info("SIP客户端初始化成功")
        except pj.Error as e:
            logger.error(f"初始化PJSIP失败: {e}")
            if hasattr(e, 'info'):
                logger.error(f"详细错误信息: {e.info()}")
            raise
        except Exception as e:
            logger.error(f"初始化PJSIP过程中出现非PJSIP错误: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            raise

    def set_whisper_model(self, model):
        """设置Whisper模型"""
        self.whisper_model = model
        
    def make_call(self, number, voice_file=None, response_voice_file=None):
        """拨打电话并播放语音"""
        try:
            if self.current_call:
                logger.warning("已有通话在进行中")
                return False

            # 检查SIP账户是否注册成功
            try:
                acc_info = self.acc.getInfo()
                if acc_info.regStatus != pj.PJSIP_SC_OK:
                    logger.error(f"SIP账户未注册成功，状态码: {acc_info.regStatus}")
                    logger.error("在注册成功前不能拨打电话")
                    return False
            except Exception as e:
                logger.error(f"获取SIP账户状态失败: {e}")
                return False
                
            # 构建SIP URI
            if number.startswith("sip:"):
                # 已经是完整的SIP URI
                sip_uri = number
                logger.info(f"使用原始SIP URI: {sip_uri}")
            else:
                # 清理号码，只保留数字和拨号字符
                clean_number = ''.join(c for c in number if c.isdigit() or c in ['+', '*', '#'])
                
                # 构建完整SIP URI
                sip_uri = f"sip:{clean_number}@{self.config['server']}:{self.config['port']}"
                logger.info(f"构建SIP URI: {sip_uri}")
            
            # 详细日志
            logger.info(f"=== 开始拨号 ===")
            logger.info(f"目标号码: {number}")
            logger.info(f"SIP URI: {sip_uri}")
            logger.info(f"SIP账户: {self.config['username']}@{self.config['server']}:{self.config['port']}")
            if voice_file:
                logger.info(f"语音文件: {voice_file}")
            
            # 创建通话对象，并传入电话号码和响应语音文件
            call = SIPCall(self.acc, voice_file, self.whisper_model, number, response_voice_file)
            
            # 设置呼叫参数
            call_prm = pj.CallOpParam(True)  # 使用默认值
            call_prm.opt.audioCount = 1
            call_prm.opt.videoCount = 0
            
            # 开始拨号
            logger.info(f"发送拨号请求: {sip_uri}")
            call.makeCall(sip_uri, call_prm)
            logger.info("拨号请求已发送")
            
            self.current_call = call
            self.phone_number = number
            
            # 等待呼叫状态变化
            logger.info("等待呼叫状态变化...")
            for i in range(10):
                if not call.isActive():
                    logger.warning(f"呼叫已不再活跃 [{i}秒]")
                    break
                    
                try:
                    ci = call.getInfo()
                    state_names = {
                        pj.PJSIP_INV_STATE_NULL: "NULL",
                        pj.PJSIP_INV_STATE_CALLING: "CALLING",
                        pj.PJSIP_INV_STATE_INCOMING: "INCOMING",
                        pj.PJSIP_INV_STATE_EARLY: "EARLY",
                        pj.PJSIP_INV_STATE_CONNECTING: "CONNECTING",
                        pj.PJSIP_INV_STATE_CONFIRMED: "CONFIRMED",
                        pj.PJSIP_INV_STATE_DISCONNECTED: "DISCONNECTED"
                    }
                    state_name = state_names.get(ci.state, f"未知状态({ci.state})")
                    
                    logger.info(f"呼叫状态 [{i}秒]: {state_name}, 状态码: {ci.lastStatusCode}, 原因: {ci.lastReason}")
                    
                    # 如果通话已确认
                    if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
                        logger.info("通话已接通")
                        break
                        
                    # 如果通话已断开
                    if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                        logger.error(f"通话已断开: 状态码={ci.lastStatusCode}, 原因={ci.lastReason}")
                        return False
                except Exception as e:
                    logger.warning(f"获取呼叫状态时出错: {e}")
                    
                time.sleep(1)
                
            logger.info("呼叫过程完成")
            return self.current_call and self.current_call.isActive()
                
        except pj.Error as e:
            logger.error(f"拨打电话失败: {e}")
            # 输出详细错误信息
            if hasattr(e, 'status') and hasattr(e, 'reason'):
                logger.error(f"SIP错误状态: {e.status}, 原因: {e.reason}")
            else:
                logger.error(f"完整错误信息: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"拨号过程中发生未知错误: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False

    def hangup(self):
        """挂断当前通话"""
        try:
            if self.current_call:
                call_prm = pj.CallOpParam()
                self.current_call.hangup(call_prm)
                self.current_call = None
                logger.info("通话已挂断")
                return True
            else:
                logger.warning("没有正在进行的通话")
                return False
        except pj.Error as e:
            logger.error(f"挂断通话失败: {e}")
            return False

    def stop(self):
        """停止PJSIP"""
        try:
            if self.acc:
                try:
                    # 使用正确的方法删除账户
                    self.acc.setRegistration(False)
                    time.sleep(1)  # 等待注销完成
                    self.acc = None
                except Exception as e:
                    logger.warning(f"删除账户时出错: {e}")
                    self.acc = None
            if self.ep:
                try:
                    self.ep.libDestroy()
                except Exception as e:
                    logger.warning(f"销毁PJSIP库时出错: {e}")
                    self.ep = None
            logger.info("SIP服务已停止")
        except Exception as e:
            logger.error(f"停止SIP服务失败: {e}")
            self.acc = None
            self.ep = None 

class MyAudioMediaPort(pj.AudioMediaPort):
    """自定义音频媒体端口类，用于实时转录"""
    def __init__(self, whisper_model=None, call=None):
        pj.AudioMediaPort.__init__(self)
        self.whisper_model = whisper_model
        self.realtime_chunks_dir = "realtime_chunks"
        self.transcription_active = False
        self.current_chunk_file = None
        self.chunk_recorder = None
        self.is_chunk_recording = False
        self.buffer = bytearray()
        self.buffer_size = 0
        self.last_transcription_time = 0
        self.chunk_duration = 2  # 缩短每个音频块的秒数，提高实时性
        self.sample_rate = 8000
        self.bytes_per_sample = 2  # 16位PCM
        self.transcription_thread = None
        self.call = call
        self.silence_threshold = 500  # 静音阈值（字节数）
        self.silence_duration = 1.5  # 静音持续时间（秒）
        self.last_sound_time = 0  # 上次检测到声音的时间
        self.has_detected_speech = False  # 是否检测到过语音
        self.speech_ended = False  # 对方是否说完第一句话
        self.should_play_response = False  # 是否应该播放回复
        self.last_speech_time = 0  # 上次检测到语音结束的时间
        self.process_lock = threading.Lock()  # 添加锁以避免线程冲突
        self.accumulated_speech = ""  # 累积的语音识别结果
        
        # 创建转录文件夹
        os.makedirs(self.realtime_chunks_dir, exist_ok=True)
    
    def _initialize_resources(self):
        """初始化资源"""
        try:
            # 清空之前的临时文件
            for f in os.listdir(self.realtime_chunks_dir):
                try:
                    os.remove(os.path.join(self.realtime_chunks_dir, f))
                except:
                    pass
                
            self.buffer = bytearray()
            self.buffer_size = 0
            self.last_transcription_time = time.time()
            logger.info("实时转录资源已初始化")
        except Exception as e:
            logger.error(f"初始化实时转录资源时出错: {e}")
    
    def start_realtime_transcription(self, call):
        """启动实时语音转录线程"""
        self.call = call
        self._initialize_resources()
        
        # 创建转录文件夹
        os.makedirs(self.realtime_chunks_dir, exist_ok=True)
        
        # 清空之前的临时文件
        for f in os.listdir(self.realtime_chunks_dir):
            try:
                os.remove(os.path.join(self.realtime_chunks_dir, f))
            except:
                pass
        
        # 设置状态变量
        self.transcription_active = True
        self.is_chunk_recording = False
        self.chunk_recorder = None
        self.current_chunk_file = None
        
        # 获取媒体
        if not call:
            logger.error("无法启动转录：未提供有效的通话对象")
            return False
        
        try:
            # 不使用音频媒体直接传输，而是在回调中注册本地回调来处理
            logger.info("已启用实时转录，将在音频回调中处理数据...")
            
            # 启动处理线程
            self.transcription_thread = threading.Thread(
                target=self._process_audio_data_loop,
                daemon=True
            )
            self.transcription_thread.start()
            
            # 注册通话中音频数据的回调处理，在onCallMediaState中实现
            logger.info("实时转录准备就绪，等待音频数据...")
            return True
                
        except Exception as e:
            logger.error(f"启动实时转录时出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
        
        return False

    def _process_audio_data_loop(self):
        """处理音频数据的线程循环，不调用PJSIP API"""
        logger.info("开始音频处理循环")
        try:
            # 主循环
            while self.transcription_active:
                with self.process_lock:
                    # 检查是否有足够的数据进行转录
                    current_time = time.time()
                    if current_time - self.last_transcription_time >= self.chunk_duration and self.buffer_size > 1000:
                        # 转录当前数据块
                        self._process_buffer_directly()
                        self.last_transcription_time = current_time
                    
                    # 检查是否为静音
                    elif self.has_detected_speech and not self.speech_ended:
                        if current_time - self.last_sound_time > self.silence_duration:
                            logger.info("检测到对方说话结束")
                            self.speech_ended = True
                            self.last_speech_time = current_time
                            self.should_play_response = True
                            
                            # 最后一次转录，确保捕获所有内容
                            if self.buffer_size > 0:
                                self._process_buffer_directly()
                            
                            # 输出完整的转录结果
                            if self.accumulated_speech:
                                logger.info(f"完整转录结果: {self.accumulated_speech}")
                            
                            # 通知SIPCall对象播放回复
                            if self.call and hasattr(self.call, "play_response_after_speech"):
                                threading.Thread(target=self.call.play_response_after_speech, daemon=True).start()
                
                time.sleep(0.1)  # 减少CPU使用
                
        except Exception as e:
            logger.error(f"音频处理循环出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
        finally:
            self.transcription_active = False
            logger.info("音频处理循环已结束")
    
    def _process_buffer_directly(self):
        """直接处理当前缓冲区中的音频数据进行转录，完全在内存中进行"""
        if not self.buffer or self.buffer_size < 1000:  # 小于1000字节的数据可能没有有用信息
            return
            
        try:
            # 更新最后一次检测到声音的时间
            self.last_sound_time = time.time()
            if not self.has_detected_speech:
                self.has_detected_speech = True
                logger.info("检测到对方开始说话")
            
            # 使用Whisper实时转录
            if self.whisper_model:
                # 创建内存中的音频数据，无需写入临时文件
                import io
                import numpy as np
                
                # 将PCM数据转换为numpy数组
                audio_data = np.frombuffer(bytes(self.buffer), dtype=np.int16)
                
                # 转换为float32并归一化到[-1, 1]区间
                audio_float = audio_data.astype(np.float32) / 32768.0
                
                # 如果需要，可以在这里进行一些预处理，如降噪、音量归一化等
                
                # 调用Whisper API直接处理内存中的音频数据
                result = self.whisper_model.transcribe(audio_float, sampling_rate=self.sample_rate)
                text = result.get('text', '').strip()
                    
                if text:
                    logger.info(f"实时转录片段: {text}")
                    # 累积转录结果
                    if self.accumulated_speech:
                        self.accumulated_speech += " " + text
                    else:
                        self.accumulated_speech = text
            
            # 清空缓冲区，准备接收新的音频数据
            self.buffer = bytearray()
            self.buffer_size = 0
                
        except Exception as e:
            logger.error(f"实时转录处理出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            # 出错时也清空缓冲区，避免数据堆积
            self.buffer = bytearray()
            self.buffer_size = 0
    
    def onFrameRequested(self, frame):
        """当需要音频帧时调用（源）"""
        # 作为源端口，这里不需要实现任何功能
        pass
        
    def onFrameReceived(self, frame):
        """当接收到音频帧时调用（接收器）"""
        if not self.transcription_active:
            return
            
        try:
            # 获取帧数据
            frame_data = frame.buf
            frame_len = frame.size
            
            # 检查是否有足够的数据进行处理
            if frame_len <= 0:
                return
                
            with self.process_lock:
                # 将帧数据添加到缓冲区
                self.buffer.extend(frame_data[:frame_len])
                self.buffer_size += frame_len
            
        except Exception as e:
            logger.error(f"处理接收到的音频帧时出错: {e}")