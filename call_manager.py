import os
import time
import csv
import logging
from datetime import datetime

logger = logging.getLogger("call_manager")

class CallManager:
    def __init__(self, sip_caller, tts_manager, whisper_manager):
        """呼叫管理器"""
        self.sip_caller = sip_caller
        self.tts_manager = tts_manager
        self.whisper_manager = whisper_manager
        self.call_list = []
        self.call_results = []
        self.current_index = 0
        
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
            
    def save_call_results(self, file_path):
        """保存呼叫结果"""
        try:
            # 确定文件是否已存在
            file_exists = os.path.exists(file_path)
            
            with open(file_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # 如果文件不存在，写入表头
                if not file_exists:
                    writer.writerow(['电话号码', '呼叫时间', '呼叫状态', '接通时长', '录音文件', '语音识别结果'])
                
                # 写入所有结果
                for result in self.call_results:
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
            
    def make_call_with_tts(self, phone_number, text, voice="zh-CN-XiaoxiaoNeural"):
        """使用TTS拨打电话"""
        try:
            # 生成语音文件
            wav_file = self.tts_manager.generate_tts_sync(text, voice)
            if not wav_file:
                logger.error("TTS生成失败，无法拨打电话")
                return None
                
            # 设置Whisper模型
            self.sip_caller.set_whisper_model(self.whisper_manager.model)
                
            # 记录开始时间
            start_time = datetime.now()
            
            # 拨打电话
            call_result = self.sip_caller.make_call(phone_number, wav_file)
            
            # 初始化结果
            result = {
                'phone_number': phone_number,
                'call_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'status': '接通' if call_result else '未接通',
                'duration': '',
                'recording': '',
                'transcription': ''
            }
            
            # 如果接通成功，等待通话结束
            if call_result:
                # 等待通话结束
                while self.sip_caller.current_call:
                    time.sleep(1)
                
                # 计算通话时长
                duration = (datetime.now() - start_time).total_seconds()
                result['duration'] = f"{duration:.1f}秒"
                
                # 获取录音文件和转录结果
                if hasattr(self.sip_caller.current_call, 'recording_file') and self.sip_caller.current_call.recording_file:
                    result['recording'] = self.sip_caller.current_call.recording_file
                    
                    # 获取转录结果
                    transcription = self.sip_caller.current_call.transcribe_audio()
                    if transcription:
                        result['transcription'] = transcription
            
            # 保存结果
            self.call_results.append(result)
            return result
            
        except Exception as e:
            logger.error(f"拨打电话失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            
            # 记录失败结果
            self.call_results.append({
                'phone_number': phone_number,
                'call_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': f'错误: {str(e)}',
                'duration': '',
                'recording': '',
                'transcription': ''
            })
            
            return None
            
    def process_calls(self, tts_text, tts_voice, log_file, interval=5):
        """处理所有呼叫"""
        if not self.call_list:
            logger.error("呼叫列表为空")
            return False
            
        logger.info(f"开始处理呼叫列表，共{len(self.call_list)}个号码")
        
        try:
            for i, phone_number in enumerate(self.call_list):
                logger.info(f"正在拨打第{i+1}个号码: {phone_number}")
                
                result = self.make_call_with_tts(phone_number, tts_text, tts_voice)
                
                # 每次呼叫后保存结果
                self.save_call_results(log_file)
                
                # 如果不是最后一个号码，等待一段时间再拨下一个
                if i < len(self.call_list) - 1:
                    logger.info(f"等待{interval}秒后拨打下一个号码...")
                    time.sleep(interval)
                    
            logger.info("所有呼叫已处理完成")
            return True
            
        except Exception as e:
            logger.error(f"处理呼叫列表过程中出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False 