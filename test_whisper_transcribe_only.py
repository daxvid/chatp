import whisper
import time
import os
import logging
from pathlib import Path
import traceback
import urllib.request
import ssl
import torch  # 添加torch导入

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("whisper_test")

# 检测CUDA是否可用
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"使用设备: {DEVICE}")
if DEVICE == "cuda":
    gpu_name = torch.cuda.get_device_name(0)
    logger.info(f"GPU型号: {gpu_name}")

# 禁用证书验证，解决可能的SSL问题
ssl._create_default_https_context = ssl._create_unverified_context

def download_with_retry(url, dest, max_retries=3):
    """下载文件，支持重试"""
    for attempt in range(max_retries):
        try:
            logger.info(f"下载 {url} 到 {dest}，尝试 {attempt+1}/{max_retries}")
            urllib.request.urlretrieve(url, dest)
            return True
        except Exception as e:
            logger.error(f"下载失败 ({attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(2)  # 重试前短暂等待
    return False

def load_model_with_retry(model_name, model_dir, max_retries=3):
    """加载模型，支持重试"""
    for attempt in range(max_retries):
        try:
            logger.info(f"加载 {model_name} 模型，尝试 {attempt+1}/{max_retries}...")
            model = whisper.load_model(model_name, device=DEVICE, download_root=str(model_dir))
            logger.info(f"{model_name} 模型加载成功")
            return model
        except Exception as e:
            logger.error(f"{model_name} 模型加载失败 ({attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                logger.error(f"详细错误: {traceback.format_exc()}")
                return None
            time.sleep(2)  # 重试前短暂等待
    return None

def check_model_files(model_name, model_dir):
    """检查模型文件是否已存在于本地"""
    model_path = Path(model_dir) / f"{model_name}.pt"
    return model_path.exists()

def main():
    """测试不同Whisper模型的转录性能，只计算转录时间"""
    # 测试音频文件
    audio_file = "recordings/test.wav"
    
    # 检查音频文件是否存在
    if not os.path.exists(audio_file):
        logger.error(f"测试音频文件不存在: {audio_file}")
        return
    
    # 创建模型目录
    model_dir = Path("models/whisper")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    # 要测试的模型列表
    models = ["tiny", "base", "small", "turbo"]
    
    # 存储结果
    results = []
    
    # 检查哪些模型已经存在
    existing_models = []
    for model_name in models:
        if check_model_files(model_name, model_dir):
            logger.info(f"模型 {model_name} 已存在于本地")
            existing_models.append(model_name)
        else:
            logger.info(f"模型 {model_name} 需要下载")
    
    if not existing_models:
        logger.warning("没有本地可用的模型，需要下载模型文件")
    
    # 先加载所有模型
    loaded_models = {}
    for model_name in models:
        model = load_model_with_retry(model_name, model_dir)
        if model:
            loaded_models[model_name] = model
        else:
            logger.error(f"无法加载 {model_name} 模型，将跳过测试")
    
    if not loaded_models:
        logger.error("没有成功加载任何模型，测试终止")
        return
    
    # 测试各模型的转录性能
    for model_name, model in loaded_models.items():
        logger.info(f"\n测试 {model_name} 模型转录性能...")
        
        try:
            # 只测量转录时间
            transcribe_start = time.time()
            result = model.transcribe(
                audio_file,
                language="zh",
                fp16=True,  # 启用半精度浮点数加速
            )
            transcribe_time = time.time() - transcribe_start
            
            # 显示结果
            logger.info(f"模型: {model_name}")
            logger.info(f"转录时间: {transcribe_time:.2f} 秒")
            logger.info(f"转录结果: {result['text'][:100]}...")
            logger.info("-" * 50)
            
            # 收集结果
            results.append({
                "model": model_name,
                "transcribe_time": transcribe_time,
                "text": result["text"][:100]
            })
            
        except Exception as e:
            logger.error(f"{model_name} 模型测试失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
    
    # 显示比较结果
    if results:
        logger.info("\n性能比较结果 (只计算转录时间):")
        logger.info("模型名称\t转录时间(秒)")
        logger.info("-" * 40)
        
        for r in results:
            logger.info(f"{r['model']}\t{r['transcribe_time']:.2f}")
    else:
        logger.error("没有成功完成任何模型的测试")

if __name__ == "__main__":
    main() 