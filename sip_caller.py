import pjsua2 as pj
import time
import os
import wave
import logging
import ssl
from datetime import datetime

# 禁用SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

logger = logging.getLogger("sip")

class SIPCall(pj.Call):
    """SIP通话类，继承自pjsua2.Call"""
    def __init__(self, acc, voice_file=None, whisper_model=None):
        pj.Call.__init__(self, acc)
        self.voice_file = voice_file
        self.voice_data = None
        self.recorder = None
        self.recording_file = None
        self.whisper_model = whisper_model
        
        if self.voice_file:
            self._load_voice_file()

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
            
            # 连接到通话
            call_media = self.getAudioVideoStream()[0]
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
                if self.voice_file and os.path.exists(self.voice_file):
                    try:
                        # 创建音频播放器
                        player = pj.AudioMediaPlayer()
                        logger.info(f"尝试播放语音文件: {self.voice_file}")
                        
                        # 加载并检查语音文件
                        try:
                            player.createPlayer(self.voice_file)
                            logger.info("语音播放器已创建")
                        except Exception as e:
                            logger.error(f"创建播放器失败: {e}")
                            return
                            
                        # 等待确保通话流建立
                        time.sleep(0.5)
                        
                        # 获取通话媒体
                        try:
                            audio_stream = self.getAudioMedia(-1)
                            logger.info("成功获取音频媒体")
                        except Exception as e:
                            logger.error(f"获取音频媒体失败: {e}")
                            
                            # 尝试通过另一种方式获取
                            try:
                                audio_stream = self.getAudioVideoStream()[0]
                                logger.info("通过备选方法获取到音频流")
                            except Exception as e2:
                                logger.error(f"获取音频流失败: {e2}")
                                return
                        
                        # 开始传输音频
                        player.startTransmit(audio_stream)
                        logger.info("开始播放语音，音频传输已启动")
                        
                        # 开始录音
                        if prm and hasattr(prm, 'remoteUri') and prm.remoteUri:
                            self.start_recording(prm.remoteUri)
                        else:
                            logger.warning("缺少远程URI信息，使用未知号码录音")
                            self.start_recording("unknown")
                            
                    except Exception as e:
                        logger.error(f"播放语音过程中出错: {e}")
                        import traceback
                        logger.error(f"详细错误: {traceback.format_exc()}")
                else:
                    logger.warning(f"语音文件不存在或未指定: {self.voice_file}")
                    
            elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                if ci.lastStatusCode >= 400:
                    logger.error(f"通话失败: 状态码={ci.lastStatusCode}, 原因={ci.lastReason}")
                else:
                    logger.info(f"通话已结束: 状态码={ci.lastStatusCode}, 原因={ci.lastReason}")
                
                # 停止录音
                self.stop_recording()
                # 转录音频
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
            sipTpConfig.port = self.config.get('bind_port', 5060)
            
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
        
    def make_call(self, number, voice_file=None):
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
            
            # 创建通话
            call = SIPCall(self.acc, voice_file, self.whisper_model)
            
            # 设置呼叫参数
            call_prm = pj.CallOpParam(True)  # 使用默认值
            call_prm.opt.audioCount = 1
            call_prm.opt.videoCount = 0
            
            # 开始拨号
            logger.info(f"发送拨号请求: {sip_uri}")
            call.makeCall(sip_uri, call_prm)
            logger.info("拨号请求已发送")
            
            self.current_call = call
            
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