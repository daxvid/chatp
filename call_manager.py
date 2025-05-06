import os
import time
import csv
import json
import redis
import logging
import traceback
import threading
import requests
from datetime import datetime
import pjsua2 as pj

logger = logging.getLogger("call_manager")

class CallManager:
    def __init__(self, sip_caller, tts_manager, whisper_manager, call_log_file, exit_event, redis_host="localhost", redis_port=6379, telegram_config=None):
        """呼叫管理器"""
        self.sip_caller = sip_caller
        self.tts_manager = tts_manager
        self.whisper_manager = whisper_manager
        self.call_log_file = call_log_file
        self.exit_event = exit_event
        self.call_list = []
        self.call_results = []
        self.current_index = 0
        
        # 初始化Redis连接
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True  # 自动解码响应为字符串
        )
        
        # Telegram配置
        self.telegram_config = telegram_config or {}
        self.telegram_bot_token = self.telegram_config.get('bot_token')
        self.telegram_chat_ids = self.telegram_config.get('chat_ids')
        
    def send_telegram_message(self, message):
        """发送Telegram消息
        
        Args:
            message: 要发送的消息内容
        """
        if not self.telegram_bot_token or not self.telegram_chat_ids:
            logger.warning("Telegram配置不完整，无法发送消息")
            return False
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            for chat_id in self.telegram_chat_ids:
                data = {
                    "chat_id": chat_id,
                    "text": message
                }
                response = requests.post(url, data=data)
                response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"发送Telegram消息失败: {e}")
            return False
            
    def load_call_list(self, file_path):
        """加载呼叫列表"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"电话号码列表文件不存在: {file_path}")
                return False
                
            with open(file_path, 'r', encoding='utf-8') as f:
                # 读取每行，去除空白字符
                self.call_list = [line.strip() for line in f if line.strip()]
                
            logger.info(f"成功加载电话号码列表，共{len(self.call_list)}个号码")
            return True
        except Exception as e:
            logger.error(f"加载电话号码列表失败: {e}")
            return False
            
    def save_call_result(self, result):
        """保存呼叫结果"""
        try:
            self.call_results.append(result)
            # 确定文件是否已存在
            file_exists = os.path.exists(self.call_log_file)
            
            with open(self.call_log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # 如果文件不存在，写入表头
                if not file_exists:
                    writer.writerow(['电话号码', '开始时间', '结束时间', '呼叫状态', '接通时长', '录音文件', '转录结果'])
                
                phone = result['phone_number']
                # 写入所有结果
                writer.writerow([
                    phone,
                    datetime.fromtimestamp(result['start']).strftime("%Y%m%d_%H%M%S"),
                    datetime.fromtimestamp(result['end']).strftime("%Y%m%d_%H%M%S"),
                    result['status'],
                    result.get('duration', '0'),
                    result.get('record', '--'),
                    result.get('text', '--')
                ])
            
            # 如果通话成功接通，将结果保存到Redis并发送Telegram通知
            if result['status'] == '接通':
                try:
                    # 生成唯一的通话记录ID
                    call_id = f"call:{phone}:{int(result['start'])}"
                    url_time = result.get('play_url_time', None)
                    # 准备要保存的数据
                    call_data = {
                        'phone': phone,
                        'start': datetime.fromtimestamp(result['start']).isoformat(),
                        'end': datetime.fromtimestamp(result['end']).isoformat(),
                        'status': result['status'],
                        'duration': result.get('duration', '0'),
                        'record': result.get('record', '--'),
                        'text': result.get('text', '--'),
                        'confirmed': datetime.fromtimestamp(result['confirmed']).isoformat() if result.get('confirmed') else None,
                        'play_url_time': url_time
                    }
                    
                    # 保存到Redis
                    self.redis_client.set(call_id, json.dumps(call_data, ensure_ascii=False))
                    logger.info(f"通话结果已保存到Redis: {call_id}")
                    
                    # 如果有播放下载地址,则发送Telegram通知
                    if url_time:
                        #将电话的第4/5/6位数字隐藏
                        phone_hide = phone[:3] + '***' + phone[6:]
                        message = (
                            f"🟢 电话: {phone_hide}\n"
                            f"⏱ 时长: {result.get('duration', '60')}\n"
                        )
                        self.send_telegram_message(message)
                    
                except Exception as e:
                    logger.error(f"保存通话结果到Redis或发送Telegram通知失败: {e}")
                    
            logger.info(f"呼叫结果已保存到: {self.call_log_file}")
            return True
        except Exception as e:
            logger.error(f"保存呼叫结果失败: {e}")
            return False
            
    def make_call(self, phone_number):
        """使用TTS拨打电话"""
        try:
            # 拨打电话
            logger.info(f"开始拨打电话: {phone_number}")
            call = self.sip_caller.make_call(phone_number)
            # 如果呼叫建立成功，等待通话完成
            if call:
                timeout = 600
                call_start = time.time()
                logger.info(f"电话 {phone_number} 呼叫建立，等待通话完成...")
                while call.is_active():
                    # 检查退出请求
                    if self.exit_event.is_set():
                        logger.info("检测到退出请求，中断当前通话")
                        call.hangup()
                        break
                    
                    # 检查通话时间是否超时
                    if time.time() - call_start > timeout:
                        logger.warning(f"通话时间超过{timeout}秒，强制结束")
                        call.hangup()
                        break

                    count = call.voice_check()
                    if count == 0:
                        time.sleep(0.1)

                # 等待转录完成
                while not call.done:
                    time.sleep(0.1)
                
                # 从SIPCall获取呼叫结果
                result = call.call_result
                logger.info(f"电话 {phone_number} 处理完成: 状态={result['status']}, 时长={result['duration']}")
                return result
            else:
                logger.warning(f"电话 {phone_number} 拨打失败")
            
            # 处理失败情况
            return {
                'phone_number': phone_number,
                'start': call_start,
                'end': time.time(),
                'status': '未接通',
                'duration': '--',
                'record': '--',
                'text': '--'
            }
            
        except Exception as e:
            logger.error(f"拨打电话失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            # 记录失败结果
            return {
                'phone_number': phone_number,
                'start': call_start,
                'end': time.time(),
                'status': f'错误: {str(e)}',
                'duration': '--',
                'record': '--',
                'text': '--'
            }
            