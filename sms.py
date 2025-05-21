import logging
import yaml
import aiohttp
from typing import List, Optional, Dict, Union
from urllib.parse import urlencode

logger = logging.getLogger("sms")

class SMSError(Exception):
    """短信发送异常"""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"短信发送失败: {code} - {message}")

class SMSClient:
    """短信发送客户端"""
    
    # 错误码映射
    ERROR_CODES = {
        "0": "发送成功",
        "1": "提交参数不能为空",
        "2": "账号无效或未开户",
        "3": "账号密码错误",
        "4": "预约发送时间无效",
        "5": "IP不合法",
        "6": "号码中含有无效号码或不在规定的号段",
        "7": "内容中含有非法关键字",
        "8": "内容长度超过上限",
        "9": "接受号码过多",
        "10": "黑名单用户",
        "11": "提交速度太快",
        "12": "您尚未订购[普通短信业务]",
        "13": "您的[普通短信业务]剩余数量发送不足",
        "14": "流水号格式不正确",
        "15": "流水号重复",
        "16": "超出发送上限",
        "17": "余额不足",
        "18": "扣费不成功",
        "20": "系统错误",
        "21": "只能发送联通的手机号码",
        "22": "只能发送移动的手机号码",
        "23": "只能发送电信的手机号码",
        "24": "账户状态不正常",
        "25": "账户权限不足",
        "26": "需要人工审核",
        "28": "发送内容与模板不符"
    }

    def __init__(self, sms_config):
        """初始化短信客户端
        
        Args:
            sms_config: 短信配置字典
        """
        self.sms_config = sms_config

    async def send_sms(
        self,
        phone_numbers: Union[str, List[str]],
        content: str,
        schedule_time: Optional[str] = None,
        serial_number: Optional[str] = None
    ) -> Dict[str, str]:
        """发送短信
        
        Args:
            phone_numbers: 手机号码，可以是单个号码字符串或号码列表
            content: 短信内容
            schedule_time: 预约发送时间，格式：yyyyMMddhhmmss
            serial_number: 流水号，20位数字

        Returns:
            Dict[str, str]: 包含 result, description, taskid 的响应字典

        Raises:
            SMSError: 发送失败时抛出异常
        """
        try:
            # 处理手机号码
            if isinstance(phone_numbers, list):
                phone_numbers = ','.join(phone_numbers)

            if len(content) == 0:
                content = self.sms_config['content']
            
            # 验证内容长度
            if len(content) > 700:
                raise SMSError("8", "内容长度超过上限，最大700个字符")
            
            # 验证号码数量
            if len(phone_numbers.split(',')) > 1000:
                raise SMSError("9", "接受号码过多，最多1000个号码")

            # 准备请求参数
            params = {
                'SpCode': self.sms_config['sp_code'],
                'LoginName': self.sms_config['login_name'],
                'Password': self.sms_config['password'],
                'MessageContent': content,
                'UserNumber': phone_numbers,
            }

            # 添加可选参数
            if schedule_time:
                params['ScheduleTime'] = schedule_time
            if serial_number:
                params['SerialNumber'] = serial_number
            if self.sms_config.get('sub_port'):
                params['subPort'] = self.sms_config['sub_port']

            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.sms_config['api_url'],
                    data=params,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                ) as response:
                    if response.status != 200:
                        raise SMSError("20", f"HTTP请求失败: {response.status}")
                    
                    result = await response.json()
                    
                    # 检查发送结果
                    if result['result'] != "0":
                        error_msg = self.ERROR_CODES.get(
                            result['result'],
                            f"未知错误: {result['description']}"
                        )
                        raise SMSError(result['result'], error_msg)
                    
                    logger.info(f"短信发送成功: {result}")
                    return result

        except aiohttp.ClientError as e:
            logger.error(f"发送短信请求失败: {e}")
            raise SMSError("20", f"网络请求错误: {str(e)}")
        except Exception as e:
            logger.error(f"发送短信时出错: {e}")
            raise

    def send_sms_sync(
        self,
        phone_numbers: Union[str, List[str]],
        content: str = "",
        schedule_time: Optional[str] = None,
        serial_number: Optional[str] = None
    ) -> Dict[str, str]:
        """同步版本的短信发送函数
        
        Args:
            phone_numbers: 手机号码，可以是单个号码字符串或号码列表
            content: 短信内容，如果为空则使用配置中的默认内容
            schedule_time: 预约发送时间，格式：yyyyMMddhhmmss
            serial_number: 流水号，20位数字

        Returns:
            Dict[str, str]: 包含 result, description, taskid 的响应字典

        Raises:
            SMSError: 发送失败时抛出异常
        """
        import asyncio
        return asyncio.run(self.send_sms(phone_numbers, content, schedule_time, serial_number))

async def send_sms(
    phone_numbers: Union[str, List[str]],
    content: str,
    schedule_time: Optional[str] = None,
    serial_number: Optional[str] = None,
    config_path: str = 'conf/config.yaml'
) -> Dict[str, str]:
    """便捷的短信发送函数
    
    Args:
        phone_numbers: 手机号码，可以是单个号码字符串或号码列表
        content: 短信内容
        schedule_time: 预约发送时间，格式：yyyyMMddhhmmss
        serial_number: 流水号，20位数字
        config_path: 配置文件路径

    Returns:
        Dict[str, str]: 包含 result, description, taskid 的响应字典

    Raises:
        SMSError: 发送失败时抛出异常
    """
    client = SMSClient(config_path)
    return await client.send_sms(phone_numbers, content, schedule_time, serial_number)

def send_sms_sync(
    phone_numbers: Union[str, List[str]],
    content: str = "",
    schedule_time: Optional[str] = None,
    serial_number: Optional[str] = None,
    config_path: str = 'conf/config.yaml'
) -> Dict[str, str]:
    """同步版本的便捷短信发送函数
    
    Args:
        phone_numbers: 手机号码，可以是单个号码字符串或号码列表
        content: 短信内容，如果为空则使用配置中的默认内容
        schedule_time: 预约发送时间，格式：yyyyMMddhhmmss
        serial_number: 流水号，20位数字
        config_path: 配置文件路径

    Returns:
        Dict[str, str]: 包含 result, description, taskid 的响应字典

    Raises:
        SMSError: 发送失败时抛出异常
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        client = SMSClient(config['sms'])
        return client.send_sms_sync(phone_numbers, content, schedule_time, serial_number)
    except Exception as e:
        logger.error(f"发送短信时出错: {e}")
        raise

# 使用示例
if __name__ == '__main__':
    import asyncio
    
    async def test_send():
        try:
            # 发送单个号码
            result = await send_sms(
                "13300000000",
                "测试短信内容"
            )
            print(f"发送结果: {result}")
            
            # 发送多个号码
            result = await send_sms(
                ["13300000000", "13800000000"],
                "测试群发短信"
            )
            print(f"群发结果: {result}")
            
        except SMSError as e:
            print(f"发送失败: {e}")
        except Exception as e:
            print(f"发生错误: {e}")
    
    asyncio.run(test_send()) 