from pyVoIP.credentials import CredentialsManager
from pyVoIP.VoIP.call import VoIPCall
from pyVoIP.VoIP.error import InvalidStateError
from pyVoIP.VoIP.phone import VoIPPhone, VoIPPhoneParameter
import time
import yaml
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Call(VoIPCall):
    def ringing(self, invite_request):
        try:
            self.answer()
            self.hangup()
        except InvalidStateError:
            pass

class VoIPCaller:
    def __init__(self, config_path="config.yaml"):
        # 加载配置
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 初始化凭证管理器
        self.cm = CredentialsManager()
        self.cm.add(
            self.config['sip']['username'],
            self.config['sip']['password']
        )
        
        # 初始化SIP客户端参数
        self.params = VoIPPhoneParameter(
            self.config['sip']['server'],
            self.config['sip']['port'],
            self.config['sip']['username'],
            self.cm,
            bind_ip="0.0.0.0",
            call_class=Call
        )
        
        # 初始化SIP客户端
        self.phone = VoIPPhone(self.params)
        
        # 当前通话
        self.current_call = None

    def start(self):
        """启动SIP客户端"""
        try:
            self.phone.start()
            logger.info("SIP客户端已启动")
            return True
        except Exception as e:
            logger.error(f"启动SIP客户端失败: {e}")
            return False

    def stop(self):
        """停止SIP客户端"""
        try:
            if self.current_call:
                self.current_call.hangup()
            self.phone.stop()
            logger.info("SIP客户端已停止")
        except Exception as e:
            logger.error(f"停止SIP客户端失败: {e}")

    def on_call(self, call: VoIPCall):
        """处理来电"""
        logger.info(f"收到来电: {call.getRemoteNumber()}")
        self.current_call = call
        
        # 设置通话状态回调
        call.onStateChanged = self.on_call_state_changed
        call.onDTMFReceived = self.on_dtmf_received

    def on_call_state_changed(self, call: VoIPCall, state: str):
        """处理通话状态变化"""
        logger.info(f"通话状态改变: {state}")
        if state == "DISCONNECTED":
            self.current_call = None
        elif state == "FAILED":
            logger.error("通话失败")
            self.current_call = None

    def on_dtmf_received(self, call: VoIPCall, digit: str):
        """处理DTMF信号"""
        logger.info(f"收到DTMF信号: {digit}")

    def make_call(self, number: str):
        """拨打电话"""
        try:
            if self.current_call:
                logger.warning("已有通话在进行中")
                return False
            
            # 构建完整的SIP URI格式
            sip_uri = number #f"sip:{number}@{self.config['sip']['server']}:{self.config['sip']['port']}"
            logger.info(f"正在拨打: {sip_uri}")
            
            self.current_call = self.phone.call(sip_uri)
            
            if self.current_call:
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
    # 创建VoIP呼叫器实例
    caller = VoIPCaller()
    
    # 启动SIP客户端
    if not caller.start():
        return
    
    try:
        # 等待SIP注册完成
        time.sleep(5)
        
        # 测试拨打电话
        target_number = "13216600657"  # 替换为实际要拨打的号码
        if caller.make_call(target_number):
            # 等待通话结束
            while caller.current_call:
                time.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
    finally:
        caller.stop()

if __name__ == "__main__":
    main() 