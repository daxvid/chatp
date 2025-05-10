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
import traceback
import pydub
import subprocess
from datetime import datetime
import concurrent.futures
import whisper
from pathlib import Path
import audioop
import json
import torch
from queue import Queue

from fix_wav_in_place import fix_wav_file_in_place

# 禁用SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

logger = logging.getLogger("sip")

class CustomAudioMediaPlayer(pj.AudioMediaPlayer):
    """自定义音频播放器，用于处理播放完成回调"""
    def __init__(self):
        super().__init__()
        self.on_eof_callback = None
        
    def setEofCallback(self, callback):
        """设置播放完成回调函数"""
        self.on_eof_callback = callback
        
    def onEof2(self):
        """播放完成时的回调函数"""
        if self.on_eof_callback:
            self.on_eof_callback()

class SIPCall(pj.Call):
    """SIP通话类，继承自pjsua2.Call"""
    def __init__(self, acc, whisper_manager=None, tts_manager=None, response_manager=None, phone=None):
        pj.Call.__init__(self, acc)
        self.recorder = None
        self.recording_file = None
        self.whisper_manager = whisper_manager
        self.tts_manager = tts_manager
        self.response_manager = response_manager
        self.phone = phone
        self.audio_port = None
        self.audio_media = None
        self.ep = None
        self.player = None
        self.play_over_time = 0  # 播放完成时间
        self.last_process_time = 0  # 最后一段音频的时间
        self.chunks_size = 0     # 已保存的音频段数量
        self.talk_list = list()  # 已转录的文本内容
        self.call_time = time.time()    # 开始呼叫的时间
        self.done = False        # 是否已结
        self.play_url_times = 0 # 播放下载地址的次数
        self.is_bot = False    # 对方是否是机器人

        # 通话结果数据
        self.call_result = {
            'phone': phone,
            'start': self.call_time, # 开始呼叫时间
            'end': self.call_time,   # 结束通话时间
            'status': '未接通',
            'duration': 0,
            'code': 0,              # 状态码
            'reason': '',          # 原因
            'record': '--',
            'confirmed': None,       # 开始通话时间
            'play_url_times': 0, # 播放下载地址的次数
            'talks': None,
        }
    

        # 获取全局Endpoint实例，提前准备好
        try:
            self.ep = pj.Endpoint.instance()
        except Exception as e:
            logger.error(f"获取Endpoint实例失败: {e}")
            
    def start_recording(self):
        """开始录音"""
        if not self.audio_media:
            logger.error(f"无法获取音频媒体，无法开始录音")
            return False
        
        if self.recorder:
            logger.error(f"录音器已存在，无法开始录音")
            return False

        try:
            
            day_str = datetime.fromtimestamp(self.call_time).strftime("%Y%m%d")
            # 创建recordings目录
            recordings_dir = f"recordings/{day_str}"
            os.makedirs(recordings_dir, exist_ok=True)
            
            # 清理电话号码中的特殊字符，只保留数字
            clean_number = ''.join(filter(str.isdigit, self.phone))
            
            # 创建录音文件名，格式：电话号码_日期时间.wav
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{clean_number}_{timestamp}.wav"
            recording_file = os.path.join(recordings_dir, filename)
            
            try:
                # 创建录音器实例
                recorder = pj.AudioMediaRecorder()
                recorder.createRecorder(recording_file)
                self.audio_media.startTransmit(recorder)
                self.recording_file = recording_file
                self.recorder = recorder
                self.call_result['record'] = recording_file
                logger.info(f"录音创建成功: {recording_file}")
                return True
            except Exception as e:
                logger.error(f"创建录音失败: {e}")

        except Exception as e:
            logger.error(f"录音准备失败: {e}")

        return False
    
    def onCallMediaState(self, prm):
        """处理呼叫媒体状态改变事件"""
        try:
            ci = self.getInfo()
            logger.info(f"呼叫媒体状态改变，当前呼叫状态: {ci.stateText}")
        except Exception as e:
            logger.error(f"处理呼叫媒体状态改变时出错: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            
    def stop_recording(self):
        """停止录音"""
        try:
            if self.audio_media and self.recorder:
                self.audio_media.stopTransmit(self.recorder)
                # 停止录音
                self.recorder = None
                logger.info(f"录音已停止: {self.recording_file}")
                return True
            else: 
                return False
        except Exception as e:
            logger.error(f"停止录音失败: {e}")
            return False
    

    def response_callback(self, text, can_pass=False):
        """处理转录结果的回调函数"""
        if text:
            logger.info(f"收到转录结果: {text}")
            # 使用ResponseManager获取回复
            response_text = self.response_manager.get_response(text)
            if response_text:
                logger.info(f"匹配到回复: {response_text}")
                # 生成TTS文件
                voice_file = self.tts_manager.generate_tts_sync(response_text)
                if voice_file and os.path.exists(voice_file):
                    self.play_response_direct(response_text, voice_file, can_pass)

    def transcribe_audio(self):
        try:
            audio_file = self.recording_file
            if not os.path.exists(audio_file):
                return None

            # 创建第一个临时文件，在扩展名前加sm
            timestamp = datetime.now().strftime("_%H%M%S")
            base_name, ext = os.path.splitext(audio_file)
            temp_file = f"{base_name}{timestamp}.sm{ext}"
            if os.path.exists(temp_file):
                os.remove(temp_file)
            # 使用ffg去掉静音
            # ffmp-i input.wav -af silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-50dB output.wav
            ffmpeg_command = f"ffmpeg -i {audio_file} -af silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-50dB {temp_file}"
            subprocess.run(ffmpeg_command, shell=True, check=True)

        except Exception as e:
            logger.error(f"压缩录音文件失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None          


    def onCallConfirmed(self, prm, ci):
        logger.info("通话已接通")
        # 更新通话状态为已接通
        self.call_result['confirmed'] = time.time()
        self.call_result['end'] = time.time()
        self.call_result['status'] = '接通'
        if not self.audio_media:
            self.audio_media = self.getAudioMedia(-1)
            self.start_recording()
            # 等待1秒,开始播放第一条语音
            time.sleep(1)
            self.response_callback("播-放-开-场-欢-迎-语", False)


    def onCallDisconnected(self, prm, ci):
        logger.info("通话已结束")
        # 记录通话结束时间
        self.call_result['end'] = time.time()
        self.call_result['code'] = ci.lastStatusCode
        self.call_result['reason'] = ci.lastReason
    
        # 如果之前标记为接通，则计算通话时长
        if self.call_result['status'] == '接通':
            duration = (self.call_result['end'] - self.call_result['confirmed'])
            self.call_result['duration'] = duration #f"{duration:.1f}秒"
        
        # 停止录音
        if self.recorder:
            self.stop_recording()
            self.call_result['talks'] = self.talk_list
            # 转录通话录音并更新结果
            self.transcribe_audio()
        self.done = True

    def hangup(self):
        """挂断当前通话"""
        if self.done:
            return
        try:
            super().hangup(pj.CallOpParam())
        except Exception as e:
            logger.warning(f"挂断通话失败: {e}")

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
            
            if ci.state == pj.PJSIP_INV_STATE_CALLING:
                logger.info("正在呼叫中...")
                
            elif ci.state == pj.PJSIP_INV_STATE_EARLY:
                logger.info("对方电话开始响铃...")

            elif ci.state == pj.PJSIP_INV_STATE_CONNECTING:
                logger.info("正在建立连接...")

            elif ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
                self.onCallConfirmed(prm, ci)

            elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                self.onCallDisconnected(prm, ci)

        except Exception as e:
            logger.error(f"处理呼叫状态变化时出错: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
         
    def play_response_direct(self, response_text, voice_file, can_pass=False, leave=False):
        """播放响应音频到通话对方"""
        try:
            if not os.path.exists(voice_file):
                logger.error(f"响应语音文件不存在: {voice_file}")
                return False

            if can_pass and self.player:
                return False

            # 如果正在播放下载地址，则等待播放完成或者等待超时
            if self.player and leave == False:
                start_time = time.time()
                while self.player and time.time() - start_time < 20:
                    time.sleep(0.1)
                    # 检查通话状态
                    if self.done:
                        return False

            # 检查通话状态
            if self.done:
                return False

            # 停止当前播放
            if self.player:
                try:
                    self.player.stopTransmit(self.audio_media)
                except Exception as e:
                    logger.warning(f"停止播放失败1: {e}")
                self.play_over_time = time.time()
                self.player = None

            # 尝试立即播放，如果可能的话
            try:
                # 获取通话媒体
                audio_media = self.audio_media
                if audio_media:
                    is_play_url = "点vip" in response_text or "点tv" in response_text or "点cc" in response_text
                    # 创建自定义音频播放器
                    player = CustomAudioMediaPlayer()
                    # 使用PJMEDIA_FILE_NO_LOOP标志创建播放器
                    player.createPlayer(voice_file, pj.PJMEDIA_FILE_NO_LOOP)
            
                    # 注册播放完成回调
                    def on_playback_complete():
                        try:    
                            player.stopTransmit(audio_media)
                        except Exception as e:
                            logger.warning(f"停止播放失败2: {e}")
                        if self.player == player:
                            logger.info(f"结束播放语音: {response_text}")
                            self.play_over_time = time.time()
                            self.player = None
                            if is_play_url and self.done == False:
                                self.play_url_times += 1
                                self.call_result['play_url_times'] = self.play_url_times
                                if self.play_url_times >= 5:
                                    self.hangup()
                            if leave:
                                self.hangup()

                    player.setEofCallback(on_playback_complete)
                    # 播放到通话媒体
                    player.startTransmit(audio_media)
                    self.player = player
                    logger.info(f"开始播放语音: {response_text}")
                    return True
                else:
                    logger.warning("无法获取音频媒体，播放失败")
                    return False
            except Exception as e:
                logger.warning(f"播放语音失败: {e}")
                logger.error(f"播放语音失败，详细错误: {traceback.format_exc()}")
                return False
                
        except Exception as e:
            logger.error(f"播放响应过程中出错: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False

    def is_active(self):
        """检查通话是否活跃"""
        try:
            if not self:
                return False
            ci = self.getInfo()
            return ci.state != pj.PJSIP_INV_STATE_DISCONNECTED
        except:
            return False

    def voice_check(self):
        # 语音分段逻辑,将录音文件分段,每段至少800ms,每段结束时计算RMS值,如果低于-50 dBFS阈值,认为是静音,则保存该段,否则停止分段
        recording_file = self.recording_file
        if not (recording_file and os.path.exists(recording_file)):
            return 0

        file_size = os.path.getsize(recording_file)
        if file_size < 8*1024: 
            return 0

        base_name, ext = os.path.splitext(recording_file)
        temp_file = f"{base_name}_tmp{ext}"
        if os.path.exists(temp_file):
            os.remove(temp_file)
        shutil.copy(recording_file, temp_file)

        count = 0
        try:
            fix_wav_file_in_place(temp_file)
            audio = pydub.AudioSegment.from_wav(temp_file)
            min_silence_len = 800
            silence_thresh = -50
            chunks = pydub.silence.split_on_silence(audio, 
                min_silence_len=min_silence_len,
                silence_thresh=silence_thresh,
                keep_silence=min_silence_len
            )

            chunks_size = self.chunks_size
            if len(chunks) <= chunks_size:
                return 0
            
            talking = False
            print(f"时长:{len(audio)/1000}秒, 共:{len(chunks)} 段, 已处理{self.chunks_size},文件:{temp_file}")
            for i in range(chunks_size, len(chunks)):
                chunk = chunks[i]
                # 如果最后一段小于800ms,则表示话没说完,不保存分段
                if i == len(chunks) - 1:
                    if len(chunk) < min_silence_len:
                        talking = True
                        break
                    # 获取最后800ms的音频段
                    last_ms = chunk[-min_silence_len:]
                    # 计算最后的RMS值(均方根，表示音量大小)
                    rms = last_ms.rms
                    # 将RMS值转换为dBFS (分贝全刻度)
                    dbfs = 20 * math.log10(rms / 32768) if rms > 0 else -100
                    # 如果低于-50 dBFS阈值，认为是静音
                    if dbfs >= silence_thresh:
                        break

                chunk_file = f"{base_name}_{i}{ext}"
                chunk.export(chunk_file, format="wav")  
                logger.info(f"保存录音文件: {chunk_file}")
                self.chunks_size += 1
                result = self.whisper_manager.transcribe(chunk_file, 5)
                self.process_result(result)
                count+=1
        finally:
            os.remove(temp_file)

        if self.play_url_times < 5 and count == 0 and self.player == None and self.play_over_time > 0:
            now = time.time()
            if  now - self.play_over_time > 2 and now - self.last_process_time > 2:
                logger.info("双方都没有说话超过2秒,播放下载地址")
                if self.play_url_times == 0:
                    self.response_callback("播-放-下-载-地-址", False)
                else:
                    self.response_callback("播-放-下-载-地-址", True)

        return count
    
    def check_bot(self, talk):
        """检查对方是否是机器人"""
        if self.is_bot == False and talk:
            bot_list = ["转至语音留言", "提示音后录制留言", "机主的智能助理", "我是语音助理", "用户无法接听", "联通秘书", "通信助理", "用户无法接通"]
            for bot in bot_list:
                if bot in talk:
                    self.is_bot = True
                    response_text = self.response_manager.get_response("播-放-下-载-地-址")
                    voice_file = self.tts_manager.generate_tts_sync(response_text)
                    if voice_file and os.path.exists(voice_file):
                        self.play_response_direct(response_text, voice_file, False, True)
                    return True
        return False
    
    def process_result(self, result):
        """处理转录结果"""
        talk = ''
        try:
            if result:
                self.last_process_time = time.time()
                talk = result.get("text", "").strip()
                # 如果成功识别到文本，调用回调
                if talk and talk != '':
                    if not self.check_bot(talk):
                        self.response_callback(talk, False)
                else:
                    self.response_callback("播-放-下-载-地-址", True)
                        
        except Exception as e:
            logger.error(f"获取异步转录结果失败: {e}")
        finally:
            self.talk_list.append(talk)
            logger.info(f"获取到音频段 {len(self.talk_list)} 的转录结果: {talk[:30]}...")

    def time_out(self):
        """通话超时"""
        start = self.call_result['confirmed']
        if  start is None:
            start = self.call_time

        over_time = 116
        if self.is_bot or self.player is None:
            over_time = 56

        if time.time() - start > over_time:
            logger.info(f"通话时长超过{over_time}秒,挂断")
            self.hangup()
            return True
        return False
                       
class SIPCaller:
    """SIP呼叫管理类"""
    def __init__(self, sip_config, tts_manager=None, whisper_manager=None, response_manager=None):
        """初始化SIP客户端"""
        self.sip_config = sip_config
        self.tts_manager = tts_manager
        self.whisper_manager = whisper_manager
        self.call_history = []
        self.audio_queue = []
        
        # 初始化ResponseManager
        self.response_manager = response_manager
        
        # PJSIP相关对象
        self.ep = None
        self.acc = None
        self.call_cb = None
        
        # 转录相关
        self.recording_dir = "recordings"
        self.current_recording = None
        
        # 确保录音目录存在
        os.makedirs(self.recording_dir, exist_ok=True)
        
        # 先预生成所有可能回复的语音文件，避免因为PJSIP初始化失败而无法预生成
        if self.tts_manager:
            self._pregenerate_tts_responses()
        
        try:
            # 初始化PJSIP引擎
            logger.info("初始化PJSIP引擎...")
            self.ep = pj.Endpoint()
            self.ep.libCreate()
            
            # 配置PJSIP
            ep_cfg = pj.EpConfig()
            ep_cfg.logConfig.level = 0  # 设置日志级别为0（禁用）
            ep_cfg.logConfig.consoleLevel = 0  # 设置控制台日志级别为0（禁用）
            
            # 媒体配置
            ep_cfg.medConfig.noVad = True  # 禁用VAD（语音活动检测）
            ep_cfg.medConfig.clockRate = 8000  # 时钟频率
            ep_cfg.medConfig.sndClockRate = 8000  # 声音时钟频率
            
            # 启用无声卡模式
            ep_cfg.uaConfig.noAudioDevice = True  # 允许无音频设备启动
            
            # 初始化PJSIP库
            self.ep.libInit(ep_cfg)
            
            # 创建UDP传输
            transport_cfg = pj.TransportConfig()
            transport_cfg.port = 0  # 使用随机端口
            self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, transport_cfg)
            
            # 启动PJSIP库
            self.ep.libStart()
            
            # 配置媒体设备
            media_cfg = pj.MediaConfig()
            media_cfg.clockRate = 8000  # 媒体时钟频率
            media_cfg.sndClockRate = 8000  # 声音时钟频率
            media_cfg.channelCount = 1  # 单声道
            
            # 配置音频设备(使用空设备)
            snd_cfg = pj.AudioDevInfo()
            snd_cfg.captureDevId = -2  # 使用null设备(-1是默认设备，-2是空设备)
            snd_cfg.playbackDevId = -2  # 使用null设备
            
            try:
                logger.info("尝试配置音频设备...")
                self.ep.audDevManager().setNullDev()  # 设置空音频设备
                
                # 尝试配置音频设备，如果失败则使用空设备
                try:
                    self.ep.audDevManager().setCaptureDevById(-1)  # 尝试使用默认设备
                    self.ep.audDevManager().setPlaybackDevById(-2)  # 使用空播放设备
                except Exception as e:
                    logger.warning(f"无法配置默认录音设备，使用空设备: {e}")
                    self.ep.audDevManager().setNullDev()
            except Exception as e:
                logger.warning(f"配置音频设备出错，尝试继续: {e}")
                # 继续尝试，因为我们使用外部录音/播放机制
                
            # 注册SIP账号
            self._register_account()
            
            logger.info("SIP客户端初始化完成")
            
        except Exception as e:
            logger.error(f"SIP客户端初始化失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            # 确保资源被释放
            self.stop()
            raise

    def _register_account(self):
        """注册SIP账号"""
        try:
            # 创建账户配置
            acc_cfg = pj.AccountConfig()
            acc_cfg.idUri = f"sip:{self.sip_config['username']}@{self.sip_config['server']}:{self.sip_config['port']}"
            acc_cfg.regConfig.registrarUri = f"sip:{self.sip_config['server']}:{self.sip_config['port']}"
            acc_cfg.sipConfig.authCreds.append(
                pj.AuthCredInfo(
                    "digest",
                    "*",
                    self.sip_config['username'],
                    0,
                    self.sip_config['password']
                )
            )

            # 创建账户
            self.acc = pj.Account()
            self.acc.create(acc_cfg)

            # 等待注册完成
            max_wait = 30  # 最多等待30秒
            wait_start = time.time()
            while self.acc.getInfo().regStatus != pj.PJSIP_SC_OK:
                if time.time() - wait_start > max_wait:
                    raise Exception(f"SIP注册超时，当前状态: {self.acc.getInfo().regStatus}")
                logger.info(f"等待SIP注册完成，状态: {self.acc.getInfo().regStatus}...")
                time.sleep(0.5)

            logger.info("SIP客户端注册完成")
        except Exception as e:
            logger.error(f"注册SIP账号失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            raise

    def _pregenerate_tts_responses(self):
        """预先生成所有可能回复的语音文件"""
        try:
            logger.info("开始预生成所有可能回复的语音文件...")
            
            # 获取所有可能的回复内容
            all_responses = self.response_manager.get_all_possible_responses()
            
            if not all_responses:
                logger.warning("未找到可能的回复内容，跳过预生成语音文件")
                return
                
            logger.info(f"找到 {len(all_responses)} 条可能的回复内容")
            
            # 计数器
            success_count = 0
            fail_count = 0
            cache_count = 0

            voices = self.sip_config.get('voices', [
                'zh-CN-XiaoxiaoNeural',                
                'zh-CN-XiaoyiNeural',             
                'zh-CN-liaoning-XiaobeiNeural',         
                'zh-CN-shaanxi-XiaoniNeural',            
                'zh-TW-HsiaoChenNeural', 
            ])
            
            # 生成所有回复的语音文件
            for response_text in all_responses:
                try:
                    for voice in voices:
                        # 使用TTSManager生成语音
                        voice_file = self.tts_manager.generate_tts_sync(response_text, voice)
                        if voice_file:
                            if hasattr(self.tts_manager, 'is_from_cache') and self.tts_manager.is_from_cache(response_text):
                                cache_count += 1
                            else:
                                success_count += 1
                        else:
                            logger.warning(f"生成TTS文件失败: {response_text[:30]}...")
                            fail_count += 1
                except Exception as e:
                    logger.error(f"生成TTS文件时出错: {e}")
                    fail_count += 1
            
            logger.info(f"TTS预生成完成: 成功 {success_count} 个, 使用缓存 {cache_count} 个, 失败 {fail_count} 个")
            
        except Exception as e:
            logger.error(f"预生成TTS回复时出错: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            # 这里不抛出异常，确保即使预生成失败也能继续运行

    def make_call(self, number):
        """拨打电话"""
        try:
            # 清理数据
            number = number.strip()
            logger.info(f"=== 开始拨号 ===")
            logger.info(f"目标号码: {number}")
            
            # 构建SIP URI
            sip_uri = f"sip:{number}@{self.sip_config.get('server', '')}:{self.sip_config.get('port', '')}"
            logger.info(f"SIP URI: {sip_uri}")
            logger.info(f"SIP账户: {self.sip_config.get('username', '')}@{self.sip_config.get('server', '')}:{self.sip_config.get('port', '')}")

            # 创建通话对象，并传入电话号码和响应语音文件
            call = SIPCall(self.acc, self.whisper_manager, self.tts_manager, self.response_manager, number)
            
            # 设置呼叫参数
            call_param = pj.CallOpParam(True)

            # 发送拨号请求
            logger.info(f"发送拨号请求: {sip_uri}")
            call.makeCall(sip_uri, call_param)
            
            # 更新当前通话
            logger.info("拨号请求已发送,等待呼叫状态变化...")
            return call
        except Exception as e:
            logger.error(f"拨打电话失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None

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
