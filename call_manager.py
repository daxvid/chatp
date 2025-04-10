import os
import time
import csv
import logging
from datetime import datetime
import pjsua2 as pj

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
            logger.info(f"准备拨打电话 {phone_number}...")
            
            # 生成语音文件
            logger.info(f"生成语音: '{text[:30]}...'")
            wav_file = self.tts_manager.generate_tts_sync(text, voice)
            if not wav_file:
                logger.error("TTS生成失败，无法拨打电话")
                return None
            logger.info(f"语音文件生成成功: {wav_file}")
                
            # 设置Whisper模型
            self.sip_caller.set_whisper_model(self.whisper_manager.model)
                
            # 记录开始时间
            start_time = datetime.now()
            
            # 拨打电话
            logger.info(f"开始拨打电话: {phone_number}")
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
                logger.info(f"电话 {phone_number} 呼叫建立，等待通话完成...")
                
                # 等待通话接通或失败（最多60秒）
                call_connect_timeout = 60  # 60秒接通超时
                call_connect_start = time.time()
                
                # 等待通话状态变化
                while self.sip_caller.current_call and time.time() - call_connect_start < call_connect_timeout:
                    # 检查通话状态
                    if hasattr(self.sip_caller.current_call, 'getInfo'):
                        try:
                            call_info = self.sip_caller.current_call.getInfo()
                            # 如果通话已接通或已断开，退出等待
                            if call_info.state == pj.PJSIP_INV_STATE_CONFIRMED:
                                logger.info(f"电话 {phone_number} 已接通")
                                break
                            elif call_info.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                                logger.info(f"电话 {phone_number} 已断开连接，状态码: {call_info.lastStatusCode}")
                                break
                        except Exception as e:
                            logger.warning(f"获取呼叫状态异常: {e}")
                    
                    time.sleep(1)
                
                # 如果超时未接通，主动挂断
                if time.time() - call_connect_start >= call_connect_timeout:
                    logger.warning(f"电话 {phone_number} 接通超时，主动挂断")
                    self.sip_caller.hangup()
                    result['status'] = '接通超时'
                else:
                    # 移除这段代码 - 不在这里等待通话结束
                    # 这部分会造成并发拨号问题
                    # 因为main.py中已经有等待逻辑了
                    # 只检查通话是否已断开
                    if self.sip_caller.current_call:
                        try:
                            call_info = self.sip_caller.current_call.getInfo()
                            if call_info.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                                logger.info(f"电话 {phone_number} 已完成")
                            else:
                                logger.info(f"电话 {phone_number} 正在进行中，状态：{call_info.state}")
                        except Exception as e:
                            logger.warning(f"获取最终呼叫状态异常: {e}")
                
                # 不要再在这里挂断电话 - 由main.py控制通话结束
                # 只做状态检查和数据收集
                
                # 计算通话时长
                duration = (datetime.now() - start_time).total_seconds()
                result['duration'] = f"{duration:.1f}秒"
                
                # 检查是否有有效的呼叫对象
                if self.sip_caller.current_call:
                    # 获取录音文件和转录结果
                    if hasattr(self.sip_caller.current_call, 'recording_file') and self.sip_caller.current_call.recording_file:
                        result['recording'] = self.sip_caller.current_call.recording_file
                        
                        # 获取转录结果
                        logger.info(f"尝试转录通话录音: {result['recording']}")
                        transcription = self.sip_caller.current_call.transcribe_audio()
                        if transcription:
                            result['transcription'] = transcription
                            logger.info(f"转录结果: {transcription[:50]}...")
                        else:
                            logger.warning("无法获取转录结果")
                    else:
                        logger.warning("未找到录音文件")
                else:
                    logger.warning("呼叫对象无效，无法获取录音或转录")
            else:
                logger.warning(f"电话 {phone_number} 拨打失败")
            
            # 保存结果
            self.call_results.append(result)
            logger.info(f"电话 {phone_number} 处理完成: 状态={result['status']}, 时长={result['duration']}")
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
            
            # 确保通话已结束
            if hasattr(self, 'sip_caller') and self.sip_caller and self.sip_caller.current_call:
                self.sip_caller.hangup()
            
            return None
            
    def process_calls(self, tts_text, tts_voice, log_file, interval=5):
        """处理所有呼叫 - 已由main.py中的调用逻辑替代"""
        logger.warning("此方法已弃用，请使用main.py中的呼叫处理逻辑")
        
        if not self.call_list:
            logger.error("呼叫列表为空")
            return False
            
        logger.info(f"开始处理呼叫列表，共{len(self.call_list)}个号码")
        
        try:
            for i, phone_number in enumerate(self.call_list):
                logger.info(f"正在拨打第{i+1}个号码: {phone_number}")
                
                # 拨号，但不等待完成
                result = self.make_call_with_tts(phone_number, tts_text, tts_voice)
                
                # 每次呼叫后保存结果
                self.save_call_results(log_file)
                
                # 等待通话结束 - 这里应该交由main.py控制
                # 只是为了向后兼容才保留此方法
                if self.sip_caller.current_call and self.sip_caller.current_call.isActive():
                    logger.info(f"等待电话 {phone_number} 通话结束...")
                    # 简单等待一段时间让SIPCall回调有机会处理
                    time.sleep(5)
                    # 强制结束通话
                    self.sip_caller.hangup()
                
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