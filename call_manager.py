import os
import time
import csv
import logging
import traceback
import threading
from datetime import datetime
import pjsua2 as pj

logger = logging.getLogger("call_manager")

class CallManager:
    def __init__(self, sip_caller, tts_manager, whisper_manager, exit_event):
        """呼叫管理器"""
        self.sip_caller = sip_caller
        self.tts_manager = tts_manager
        self.whisper_manager = whisper_manager
        self.call_list = []
        self.call_results = []
        self.current_index = 0
        self.exit_event = exit_event
        
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
            
    def save_call_result(self, file_path, result):
        """保存呼叫结果"""
        try:
            self.call_results.append(result)
            # 确定文件是否已存在
            file_exists = os.path.exists(file_path)
            
            with open(file_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # 如果文件不存在，写入表头
                if not file_exists:
                    writer.writerow(['电话号码', '呼叫时间', '呼叫状态', '接通时长', '录音文件', '语音识别结果'])
                
                # 写入所有结果
                writer.writerow([
                    result['phone_number'],
                    result['call_time'],
                    result['status'],
                    result.get('duration', ''),
                    result.get('recording', ''),
                    result.get('transcription', '')
                ])
                    
            logger.info(f"呼叫结果已保存到: {file_path}")
            return True
        except Exception as e:
            logger.error(f"保存呼叫结果失败: {e}")
            return False
            
    def make_call_and_wait(self, phone_number):
        """使用TTS拨打电话"""
        try:
            # 拨打电话
            timeout = 600
            call_start_time = time.time()
            logger.info(f"开始拨打电话: {phone_number}")
            call = self.sip_caller.make_call(phone_number)
            
            # 如果呼叫建立成功，等待通话完成
            if call:
                logger.info(f"电话 {phone_number} 呼叫建立，等待通话完成...")
                while call.is_active():
                    # 检查退出请求
                    if self.exit_event.is_set():
                        logger.info("检测到退出请求，中断当前通话")
                        sip_caller.hangup()
                        break
                    
                    # 检查通话时间是否超时
                    if time.time() - call_start_time > timeout:
                        logger.warning(f"通话时间超过{timeout}秒，强制结束")
                        sip_caller.hangup()
                        break

                    count = call.voice_check()
                    if count == 0:
                        time.sleep(0.1)
                
                # 从SIPCall获取呼叫结果
                result = call.call_result
                # 保存结果
                logger.info(f"电话 {phone_number} 处理完成: 状态={result['status']}, 时长={result['duration']}")
                return result
            else:
                logger.warning(f"电话 {phone_number} 拨打失败")
            
            # 处理失败情况
            failed_result = {
                'phone_number': phone_number,
                'call_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': '未接通',
                'duration': '',
                'recording': '',
                'transcription': ''
            }
            return failed_result
            
        except Exception as e:
            logger.error(f"拨打电话失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            
            # 记录失败结果
            failed_result = {
                'phone_number': phone_number,
                'call_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': f'错误: {str(e)}',
                'duration': '',
                'recording': '',
                'transcription': ''
            }
            return failed_result
        finally:
            self.sip_caller.hangup()
            