import whisper
import time
import os
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("whisper_test")

def test_whisper_model(model_name, audio_file):
    """测试指定Whisper模型的转录性能
    
    Args:
        model_name (str): 模型名称 (tiny, base, small, turbo)
        audio_file (str): 音频文件路径
    
    Returns:
        tuple: (转录结果, 加载时间, 转录时间)
    """
    # 创建模型目录
    model_dir = Path("models/whisper")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    # 记录模型加载开始时间
    load_start = time.time()
    model = whisper.load_model(model_name, download_root=str(model_dir))
    load_time = time.time() - load_start
    
    # 记录转录开始时间
    transcribe_start = time.time()
    result = model.transcribe(
        audio_file,
        language="zh",
        fp16=True
    )
    transcribe_time = time.time() - transcribe_start
    
    return result, load_time, transcribe_time

def main():
    # 测试音频文件
    audio_file = "recordings/test.wav"
    
    # 检查音频文件是否存在
    if not os.path.exists(audio_file):
        logger.error(f"测试音频文件不存在: {audio_file}")
        return
    
    # 要测试的模型列表
    models = ["tiny", "base", "small", "turbo"]
    
    # 收集结果
    results = []
    
    # 测试各模型
    for model_name in models:
        logger.info(f"测试 {model_name} 模型...")
        
        try:
            result, load_time, transcribe_time = test_whisper_model(model_name, audio_file)
            
            # 显示结果
            logger.info(f"模型: {model_name}")
            logger.info(f"加载时间: {load_time:.2f} 秒")
            logger.info(f"转录时间: {transcribe_time:.2f} 秒")
            logger.info(f"转录结果: {result['text'][:100]}...")
            logger.info("-" * 50)
            
            # 收集结果
            results.append({
                "model": model_name,
                "load_time": load_time,
                "transcribe_time": transcribe_time,
                "text": result["text"][:100]
            })
            
        except Exception as e:
            logger.error(f"{model_name} 模型测试失败: {e}")
    
    # 显示比较结果
    logger.info("\n性能比较结果:")
    logger.info("模型名称\t加载时间(秒)\t转录时间(秒)")
    logger.info("-" * 50)
    
    for r in results:
        logger.info(f"{r['model']}\t{r['load_time']:.2f}\t{r['transcribe_time']:.2f}")

if __name__ == "__main__":
    main() 