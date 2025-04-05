import pjsua2 as pj
import whisper
import edge_tts
import asyncio
import os
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from pathlib import Path
import logging
import time
import wave
import threading

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Config:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
    @property
    def sip_config(self):
        return self.config['sip']
    
    @property
    def call_config(self):
        return self.config['call']
    
    @property
    def responses(self):
        return self.config['responses']

def load_whisper_model():
    # Create models directory if it doesn't exist
    model_dir = Path("models/whisper")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    # Set model path
    model_path = model_dir / "small.pt"
    
    # Load model from local path if exists, otherwise download
    try:
        model = whisper.load_model("small", download_root=str(model_dir))
        print(f"Loaded whisper model from {model_path}")
    except Exception as e:
        print(f"Error loading model from {model_path}: {e}")
        print("Downloading model...")
        model = whisper.load_model("small", download_root=str(model_dir))
        print("Model downloaded successfully")
    
    return model

class MyCall(pj.Call):
    def __init__(self, acc, voice_file=None):
        pj.Call.__init__(self, acc)
        self.voice_file = voice_file
        self.voice_data = None
        self.voice_position = 0
        if self.voice_file:
            self._load_voice_file()

    def _load_voice_file(self):
        """加载语音文件"""
        try:
            with wave.open(self.voice_file, 'rb') as wf:
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 8000:
                    raise ValueError("语音文件必须是单声道、16位、8kHz采样率")
                self.voice_data = wf.readframes(wf.getnframes())
                logger.info(f"语音文件加载成功: {self.voice_file}")
        except Exception as e:
            logger.error(f"加载语音文件失败: {e}")
            self.voice_data = None

    def onCallState(self, prm):
        """处理通话状态变化"""
        ci = self.getInfo()
        logger.info(f"通话状态: {ci.stateText}")
        
        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            logger.info("通话已接通")
            if self.voice_data:
                # 创建音频播放器
                player = pj.AudioMediaPlayer()
                try:
                    player.createPlayer(self.voice_file)
                    # 连接到通话
                    player.startTransmit(self.getAudioVideoStream()[0])
                except pj.Error as e:
                    logger.error(f"播放语音失败: {e}")
        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            logger.info("通话已结束")

class AutoCaller:
    def __init__(self, config_path='config.yaml'):
        self.config = self._load_config(config_path)
        self.ep = None
        self.acc = None
        self.current_call = None
        self._init_pjsua2()

    def _load_config(self, config_path):
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def _init_pjsua2(self):
        """初始化PJSIP"""
        try:
            # 创建Endpoint
            self.ep = pj.Endpoint()
            self.ep.libCreate()

            # 初始化库
            ep_cfg = pj.EpConfig()
            self.ep.libInit(ep_cfg)

            # 创建传输
            sipTpConfig = pj.TransportConfig()
            sipTpConfig.port = self.config['sip'].get('bind_port', 5060)
            self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, sipTpConfig)

            # 启动库
            self.ep.libStart()

            # 创建账户配置
            acc_cfg = pj.AccountConfig()
            acc_cfg.idUri = f"sip:{self.config['sip']['username']}@{self.config['sip']['server']}:{self.config['sip']['port']}"
            acc_cfg.regConfig.registrarUri = f"sip:{self.config['sip']['server']}:{self.config['sip']['port']}"
            acc_cfg.sipConfig.authCreds.append(
                pj.AuthCredInfo(
                    "digest",
                    "*",
                    self.config['sip']['username'],
                    0,
                    self.config['sip']['password']
                )
            )

            # 创建账户
            self.acc = pj.Account()
            self.acc.create(acc_cfg)

            # 等待注册完成
            while self.acc.getInfo().regStatus != pj.PJSIP_SC_OK:
                time.sleep(0.1)

            logger.info("SIP客户端初始化成功")
        except pj.Error as e:
            logger.error(f"初始化PJSIP失败: {e}")
            raise

    def make_call(self, number: str, voice_file: str = None):
        """拨打电话并播放语音"""
        try:
            if self.current_call:
                logger.warning("已有通话在进行中")
                return False

            # 构建SIP URI
            sip_uri = f"sip:{number}@{self.config['sip']['server']}:{self.config['sip']['port']}"
            logger.info(f"正在拨打: {sip_uri}")

            # 创建通话
            call = MyCall(self.acc, voice_file)
            call_prm = pj.CallOpParam()
            call.makeCall(sip_uri, call_prm)
            
            self.current_call = call
            logger.info("呼叫已建立")
            return True
                
        except pj.Error as e:
            logger.error(f"拨打电话失败: {e}")
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
                self.acc.delete()
            if self.ep:
                self.ep.libDestroy()
            logger.info("SIP服务已停止")
        except pj.Error as e:
            logger.error(f"停止SIP服务失败: {e}")
            raise

def main():
    try:
        # 创建自动拨号器实例
        caller = AutoCaller()
        
        # 从配置文件获取目标号码和语音文件
        target_number = caller.config['sip'].get('target_number')
        voice_file = caller.config['sip'].get('voice_file')
        
        if not target_number:
            logger.error("配置文件中未指定目标号码")
            return
            
        # 拨打电话
        if caller.make_call(target_number, voice_file):
            # 等待通话结束
            while caller.current_call:
                time.sleep(1)
        
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
    finally:
        # 确保服务被正确停止
        if 'caller' in locals():
            caller.stop()

if __name__ == "__main__":
    main() 