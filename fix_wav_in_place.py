import os
import struct
import argparse

def fix_wav_file_in_place(file_path):
    """直接在原文件上修复 WAV 文件头"""
    try:
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        # 计算正确的头部值
        data_size = file_size - 44  # 总大小减去头部大小
        chunk_size = file_size - 8   # RIFF 块大小（总大小减 8）
        
        # 以读写模式打开文件
        with open(file_path, 'r+b') as f:
            # 检查是否为 RIFF 文件
            f.seek(0)
            if f.read(4) != b'RIFF':
                f.seek(0)
                f.write(b'RIFF')
            
            # 写入正确的块大小
            f.seek(4)
            f.write(struct.pack('<I', chunk_size))
            
            # 确保 WAVE 格式标记正确
            f.seek(8)
            if f.read(4) != b'WAVE':
                f.seek(8)
                f.write(b'WAVE')
            
            # 确保 fmt 子块标记正确
            f.seek(12)
            if f.read(4) != b'fmt ':
                f.seek(12)
                f.write(b'fmt ')
            
            # 检查数据子块标记
            f.seek(36)
            if f.read(4) != b'data':
                f.seek(36)
                f.write(b'data')
            
            # 写入正确的数据大小
            f.seek(40)
            f.write(struct.pack('<I', data_size))
        return True
    except Exception as e:
        print(f"修复文件时出错: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='直接修复 WAV 文件头')
    parser.add_argument('file', help='要修复的 WAV 文件路径')
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"错误: 文件不存在: {args.file}")
        exit(1)
        
    # 修复文件
    fix_wav_file_in_place(args.file)
    
    print("修复完成！")