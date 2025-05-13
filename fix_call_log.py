import os
import re
import csv
import logging
from datetime import datetime
from pathlib import Path
import traceback

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("fix_call_log")

def parse_log_file(log_file):
    """分析日志文件，提取所有播放失败的记录"""
    play_failures = []  # 存储所有播放失败的记录
    current_call = None  # 当前正在处理的通话
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                # 匹配拨号记录，表示新通话开始
                if '=== 开始拨号 ===' in line:
                    # 如果已经有通话记录且包含播放失败，保存它
                    if current_call and current_call.get('has_failure'):
                        play_failures.append({
                            'phone': current_call['phone'],
                            'start_time': current_call['start_time'],
                            'failure_time': current_call['failure_time']
                        })
                        logger.info(f"找到播放失败记录: {current_call['phone']} at {current_call['start_time']} (失败时间: {current_call['failure_time']})")
                    
                    # 获取下一行，应该包含电话号码
                    next_line = next(f, '')
                    if '目标号码:' in next_line:
                        # 从下一行提取电话号码
                        phone = next_line.split('目标号码:')[1].strip()
                        # 开始新的通话记录
                        current_call = {
                            'phone': phone,
                            'start_time': line.split(' - ')[0],  # 获取时间戳
                            'has_failure': False,
                            'failure_time': None
                        }
                        logger.info(f"开始新通话: {current_call['phone']} at {current_call['start_time']}")
                    continue
                
                # 如果当前有通话记录
                if current_call:
                    # 检查是否包含播放失败
                    if '播放语音失败:' in line:
                        current_call['has_failure'] = True
                        current_call['failure_time'] = line.split(' - ')[0]  # 记录失败发生的时间
                        logger.info(f"在通话 {current_call['phone']} 中发现播放失败，时间: {current_call['failure_time']}")
                    
                    # 匹配通话结束记录
                    if '通话已结束' in line:
                        if current_call['has_failure']:
                            play_failures.append({
                                'phone': current_call['phone'],
                                'start_time': current_call['start_time'],
                                'failure_time': current_call['failure_time']
                            })
                            logger.info(f"通话结束，确认播放失败记录: {current_call['phone']} at {current_call['start_time']} (失败时间: {current_call['failure_time']})")
                        
                        # 重置当前通话记录
                        current_call = None
    
        # 处理最后一个通话记录
        if current_call and current_call.get('has_failure'):
            play_failures.append({
                'phone': current_call['phone'],
                'start_time': current_call['start_time'],
                'failure_time': current_call['failure_time']
            })
            logger.info(f"最后一个通话的播放失败记录: {current_call['phone']} at {current_call['start_time']} (失败时间: {current_call['failure_time']})")
    
    except Exception as e:
        logger.error(f"处理日志文件 {log_file} 时出错: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
    
    return play_failures

def fix_call_log(call_log_file, play_failures):
    """修复呼叫记录文件"""
    fixed_records = []
    modified_count = 0
    
    try:
        with open(call_log_file, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f, delimiter='\t')
            headers = next(reader)  # 读取表头
            
            # 找到状态列的索引
            status_index = headers.index('呼叫状态')
            
            for row in reader:
                if len(row) < len(headers):
                    logger.warning(f"跳过格式不正确的行: {row}")
                    continue
                
                phone = row[0]
                start_time = row[1]
                
                # 检查是否有匹配的播放失败记录
                for failure in play_failures:
                    if phone != failure['phone']:
                        continue
                        
                    try:
                        # 将时间字符串转换为datetime对象进行比较
                        call_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
                        call_start = datetime.strptime(failure['start_time'], '%Y-%m-%d %H:%M:%S,%f')
                        failure_time = datetime.strptime(failure['failure_time'], '%Y-%m-%d %H:%M:%S,%f')
                        
                        # 如果电话号码匹配且时间差在5分钟内
                        if abs((call_start - call_time).total_seconds()) < 300:
                            row[status_index] = '播放失败'
                            modified_count += 1
                            logger.info(f"修改记录: {phone} at {start_time} (失败时间: {failure_time})")
                            break
                    except ValueError as e:
                        logger.warning(f"时间格式转换错误: {e}")
                
                fixed_records.append(row)
        
        # 生成修复后的文件名
        base_name = os.path.splitext(call_log_file)[0]
        fixed_file = f"{base_name}_fix.csv"
        
        # 保存修复后的记录
        with open(fixed_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(headers)
            writer.writerows(fixed_records)
        
        logger.info(f"修复完成: {call_log_file} -> {fixed_file}")
        logger.info(f"修改了 {modified_count} 条记录")
        
        return fixed_file, modified_count
        
    except Exception as e:
        logger.error(f"处理呼叫记录文件 {call_log_file} 时出错: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        return None, 0

def main():
    """主函数"""
    # 获取log目录
    current_dir = Path('log')
    
    if not current_dir.exists():
        logger.error("log目录不存在")
        return
    
    # 查找所有需要处理的文件
    log_files = list(current_dir.glob('auto_caller*.log'))
    call_log_files = list(current_dir.glob('call_log*.csv'))
    
    if not log_files or not call_log_files:
        logger.error("在log目录中未找到需要处理的文件")
        return
    
    total_modified = 0
    
    # 处理每个日志文件
    for log_file in log_files:
        logger.info(f"\n开始处理日志文件: {log_file}")
        
        # 从日志文件名中提取编号
        match = re.search(r'auto_caller(\d{3})\.log', log_file.name)
        if not match:
            logger.warning(f"跳过无法识别的日志文件: {log_file}")
            continue
            
        file_number = match.group(1)
        
        # 查找对应的呼叫记录文件
        call_log_file = current_dir / f"call_log{file_number}.csv"
        if not call_log_file.exists():
            logger.warning(f"未找到对应的呼叫记录文件: {call_log_file}")
            continue
        
        # 分析日志文件，找出所有播放失败的记录
        logger.info(f"开始分析日志文件 {log_file} 中的播放失败记录...")
        play_failures = parse_log_file(log_file)
        logger.info(f"在 {log_file} 中找到 {len(play_failures)} 条播放失败记录")
        
        # 打印所有播放失败的记录
        for failure in play_failures:
            logger.info(f"播放失败记录: 电话 {failure['phone']}, 开始时间 {failure['start_time']}, 失败时间 {failure['failure_time']}")
        
        # 修复呼叫记录
        logger.info(f"\n开始修复呼叫记录文件 {call_log_file}...")
        fixed_file, modified = fix_call_log(call_log_file, play_failures)
        if fixed_file:
            total_modified += modified
    
    logger.info(f"\n所有文件处理完成，共修改 {total_modified} 条记录")

if __name__ == '__main__':
    main() 