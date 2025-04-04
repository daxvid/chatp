from pyVoIP.VoIP import VoIPPhone, VoIPCall
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

class VoIPCaller:
    def __init__(self, config_path="config.yaml"):
        # 加载配置
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 初始化SIP客户端
        self.phone = VoIPPhone(
            server=self.config['sip']['server'],
            port=self.config['sip']['port'],
            username=self.config['sip']['username'],
            password=self.config['sip']['password'],
            callCallback=self.on_call,
            myIP="0.0.0.0",
            proxy=self.config['sip']['server'] + ":" + str(self.config['sip']['port'])  # 添加代理服务器
        )
        
        # 设置注册刷新时间
        #self.phone.setRegisterRefresh(self.config['sip']['register_refresh'])
        
        # 设置保活时间
        #self.phone.setKeepAlive(self.config['sip']['keep_alive'])
        
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
            
            logger.info(f"正在拨打: {number}")
            
            # 设置代理认证信息
            self.phone.setProxyAuth(self.config['sip']['username'], self.config['sip']['password'])
            
            self.current_call = self.phone.call(number)
            
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