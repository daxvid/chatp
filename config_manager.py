import yaml
import os
import logging

logger = logging.getLogger("config")

class ConfigManager:
    def __init__(self, config_path='conf/config.yaml'):
        """配置管理器"""
        self.config_path = config_path
        self.config = self._load_config()
        
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"配置加载成功: {self.config_path}")
                return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise
            
    def get_sip_config(self):
        """获取SIP配置"""
        return self.config.get('sip', {})

    def get_call_list_file(self):
        """获取电话号码列表文件"""
        return self.config.get('call', {}).get('list_file', 'conf/tel.txt')
    
    def get_response_file(self):
        """获取呼叫响应配置文件"""
        return self.config.get('call', {}).get('response_file', 'conf/response.yaml') 
    
    def get_call_log_file(self):
        """获取呼叫日志文件"""
        return self.config.get('call', {}).get('log_file', 'log/call_log.csv') 
    
    def get_auto_caller_file(self):
        """获取呼叫日志文件"""
        return self.config.get('call', {}).get('auto_caller_file', 'log/auto_caller.log')
        
    def get_telegram_config(self):
        """获取Telegram配置"""
        return self.config.get('telegram', {})

    def get_whitelist_ips(self):
        """获取白名单IP"""
        return self.config.get('whitelist_ips', [])
