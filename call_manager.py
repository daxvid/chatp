import os
import time
import math
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
    def __init__(self, sip_caller, tts_manager, whisper_manager, call_log_file, exit_event, telegram_config, sms_client, redis_host="localhost", redis_port=6379):
        """呼叫管理器"""
        self.sip_caller = sip_caller
        self.tts_manager = tts_manager
        self.whisper_manager = whisper_manager
        self.call_log_file = call_log_file
        self.exit_event = exit_event
        self.call_list = []
        self.call_results = []
        self.current_index = 0
        self.sms_client = sms_client
        
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

            # 长度小于11的号码, 则从列表中删除
            self.call_list = [phone for phone in self.call_list if len(phone) >= 11]
                
            logger.info(f"成功加载电话号码列表，共{len(self.call_list)}个号码")
            return True
        except Exception as e:
            logger.error(f"加载电话号码列表失败: {e}")
            return False
            
    def save_call_result(self, result):
        """保存呼叫结果"""
        try:
            self.call_results.append(result)
            status = result['status']
            phone = result['phone']
            start = datetime.fromtimestamp(result['start']).strftime("%Y-%m-%d %H:%M:%S")
            end = datetime.fromtimestamp(result['end']).strftime("%Y-%m-%d %H:%M:%S")
            duration = math.ceil(result.get('duration', 0))
            code = result.get('code', 0)
            reason = result.get('reason', '')
            record = result.get('record', '--')
            talks = result.get('talks', None)
            text = ''
            if talks:
                text = "; ".join([f"{i+1}.{talk}" for i, talk in enumerate(talks)])

            play_url_times = result.get('play_url_times', 0)
            play_error = result.get('play_error', False)
            show_status = status
            if  duration >= 16:
                show_status = '成功'
            elif play_url_times == 0 and play_error:
                show_status = '播放失败'

            day = datetime.fromtimestamp(result['start']).strftime("%y%m%d")

            # 确定文件是否已存在
            file_exists = os.path.exists(self.call_log_file)
            with open(self.call_log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter='\t')
                # 如果文件不存在，写入表头
                if not file_exists:
                    writer.writerow(['电话号码', '开始时间', '结束时间', '呼叫状态', '接通时长', '状态码', '原因', '录音文件', '转录结果'])
                # 写入所有结果
                writer.writerow([phone, start, end, show_status, duration, code, reason, record, text])
                # 写入硬盘
                f.flush()
            
            # 如果通话成功接通，将结果保存到Redis并发送Telegram通知
            if  status == '接通':
                # 生成唯一的通话记录ID
                call_id = f"call:{day}:{phone}:{int(result['start'])}"
                confirmed = result.get('confirmed', None)
                try:
                    # 准备要保存的数据
                    call_data = {
                        'phone': phone,
                        'start': start,
                        'end': end,
                        'status': show_status,
                        'duration': duration,
                        'code': code,
                        'reason': reason,
                        'record': record,
                        'text': text,
                        'times': play_url_times,
                    }
                    if confirmed:
                        call_data['confirmed'] = datetime.fromtimestamp(confirmed).strftime("%Y-%m-%d %H:%M:%S")
                    if duration >= 16:
                        call_id = f"succ:{day}:{phone}:{int(result['start'])}"
                        
                    # 保存到Redis
                    self.redis_client.setex(call_id, 3600*24*99, json.dumps(call_data, ensure_ascii=False))
                    logger.info(f"通话已保存到Redis: {call_id}")
                except Exception as e:
                    logger.error(f"保存通话到Redis失败: {e}")

                # 如果有播放下载地址,则发送Telegram通知
                if duration >= 16:
                    try:
                        #将电话的第4/5/6位数字隐藏
                        phone_hide = phone[:3] + '***' + phone[6:]
                        message = f"🟢 通话成功: {phone_hide}"
                        if self.send_telegram_message(message):
                            logger.info(f"发送TG消息成功: {message}")
                        else:
                            logger.error(f"发送TG消息失败: {message}")
                    except Exception as e:
                        logger.error(f"发送TG消息失败: {e}")

                    # 发送短信通知
                    if self.sms_client:
                        try:
                            self.sms_client.send_sms(phone, "")
                        except Exception as e:
                            logger.error(f"发送短信失败: {e}")  

            logger.info(f"呼叫结果已保存到: {self.call_log_file}")
            return True
        except Exception as e:
            logger.error(f"保存呼叫结果失败: {e}")
            return False
            
    def make_call(self, phone):
        """使用TTS拨打电话"""
        try:
            # 拨打电话
            logger.info(f"开始拨打电话: {phone}")
            call_start = time.time()
            call = self.sip_caller.make_call(phone)
            # 如果呼叫建立成功，等待通话完成
            if call:
                logger.info(f"电话 {phone} 呼叫建立，等待通话完成...")
                while call.is_active():
                    # 检查退出请求
                    if self.exit_event.is_set():
                        logger.info("检测到退出请求，中断当前通话")
                        call.hangup()
                        break
                    
                    if call.time_out():
                        break

                    count = call.voice_check()
                    if count == 0:
                        time.sleep(0.15)

                # 等待转录完成
                while not call.done:
                    time.sleep(0.1)
                
                # 从SIPCall获取呼叫结果
                result = call.call_result
                logger.info(f"电话 {phone} 处理完成: 状态={result['status']}, 时长={result['duration']}")
                return result
            else:
                logger.warning(f"电话 {phone} 拨打失败")
            
            # 处理失败情况
            return {
                'phone': phone,
                'start': call_start,
                'end': time.time(),
                'status': '未接通',
            }
            
        except Exception as e:
            logger.error(f"拨打电话失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            # 记录失败结果
            return {
                'phone': phone,
                'start': call_start,
                'end': time.time(),
                'status': f'错误: {str(e)}',
            }
            