import yaml
import logging
import time
import wave
from pyVoIP.VoIP.phone import VoIPPhone, VoIPPhoneParameter
from pyVoIP.credentials import CredentialsManager
from pyVoIP.VoIP.call import VoIPCall
from pyVoIP.VoIP.error import InvalidStateError

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Call(VoIPCall):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.voice_file = kwargs.get('voice_file', None)
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

    def ringing(self, invite_request):
        try:
            self.answer()
            logger.info("电话已接通")
        except InvalidStateError:
            pass

    def handle_audio(self, audio_data):
        """处理音频数据"""
        if self.voice_data and self.voice_position < len(self.voice_data):
            # 获取当前要播放的音频片段
            chunk_size = len(audio_data)
            end_position = min(self.voice_position + chunk_size, len(self.voice_data))
            voice_chunk = self.voice_data[self.voice_position:end_position]
            
            # 如果语音数据不够，用静音填充
            if len(voice_chunk) < chunk_size:
                voice_chunk += b'\x00' * (chunk_size - len(voice_chunk))
            
            self.voice_position = end_position
            return voice_chunk
        return audio_data

class VoIPCaller:
    def __init__(self, config_path='config.yaml'):
        self.config = self._load_config(config_path)
        self.phone = None
        self.current_call = None
        self._init_voip_phone()

    def _load_config(self, config_path):
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def _init_voip_phone(self):
        """初始化VoIP电话"""
        try:
            # 创建凭证管理器
            cm = CredentialsManager()
            cm.add(self.config['sip']['username'], self.config['sip']['password'])

            # 创建VoIP电话参数
            params = VoIPPhoneParameter(
                self.config['sip']['server'],
                self.config['sip']['port'],
                self.config['sip']['username'],
                cm,
                bind_ip=self.config['sip'].get('bind_ip', '0.0.0.0'),
                call_class=Call
            )

            # 初始化VoIP电话
            self.phone = VoIPPhone(params)
            logger.info("SIP客户端初始化成功")
        except Exception as e:
            logger.error(f"启动SIP客户端失败: {e}")
            raise

    def start(self):
        """启动VoIP服务"""
        try:
            self.phone.start()
            logger.info("SIP服务已启动")
        except Exception as e:
            logger.error(f"启动SIP服务失败: {e}")
            raise

    def stop(self):
        """停止VoIP服务"""
        try:
            if self.phone:
                self.phone.stop()
                logger.info("SIP服务已停止")
        except Exception as e:
            logger.error(f"停止SIP服务失败: {e}")
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

            # 创建通话对象
            self.current_call = self.phone.call(sip_uri)
            
            if self.current_call:
                # 设置语音文件
                self.current_call.voice_file = voice_file
                self.current_call._load_voice_file()
                logger.info("呼叫已建立")
                return True
            else:
                logger.error("呼叫建立失败")
                return False
                
        except Exception as e:
            logger.error(f"拨打电话失败: {e}")
            return False

    def hangup(self):
        """挂断当前通话"""
        try:
            if self.current_call:
                self.current_call.hangup()
                self.current_call = None
                logger.info("通话已挂断")
                return True
            else:
                logger.warning("没有正在进行的通话")
                return False
        except Exception as e:
            logger.error(f"挂断通话失败: {e}")
            return False

def main():
    try:
        # 创建VoIP呼叫器实例
        caller = VoIPCaller()
        
        # 启动服务
        caller.start()
        
        # 等待SIP注册完成
        time.sleep(5)
        
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