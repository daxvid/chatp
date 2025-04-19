import os
import logging
import time
import ssl
import urllib.request
import traceback
from pathlib import Path
import argparse
import json
import whisper

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("whisper_downloader")

# 禁用SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

# 模型下载URL
MODEL_URLS = {
    "tiny": "https://openaipublic.azureedge.net/main/whisper/models/d3dd57d32accea0b295c96e26691aa14d8822fac7d9d27d5dc00b4ca2826dd03/tiny.pt",
    "base": "https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e/base.pt",
    "small": "https://openaipublic.azureedge.net/main/whisper/models/9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt",
    "medium": "https://openaipublic.azureedge.net/main/whisper/models/345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1/medium.pt",
    "large": "https://openaipublic.azureedge.net/main/whisper/models/e4b87e7e0bf463eb8e6956e646f1e277e901512310def2c24bf0e11bd3c28e9a/large.pt",
    "turbo": "https://openaipublic.azureedge.net/main/whisper/models/0e975e823febb7d7c3ece525fe0e505fba9c0acd1574271b1eb86893f2339a46/turbo.pt"
}

def download_with_retry(url, dest, max_retries=5):
    """下载文件并支持多次重试"""
    if os.path.exists(dest):
        file_size = os.path.getsize(dest)
        logger.info(f"文件已存在: {dest}，大小: {file_size / (1024*1024):.2f} MB")
        return True
        
    dest_dir = os.path.dirname(dest)
    os.makedirs(dest_dir, exist_ok=True)
    
    temp_dest = f"{dest}.download"
    
    for attempt in range(max_retries):
        try:
            logger.info(f"下载 {url} 到 {dest}，尝试 {attempt+1}/{max_retries}")
            
            def report_progress(block_num, block_size, total_size):
                if total_size > 0:
                    percent = min(100, block_num * block_size * 100 / total_size)
                    if block_num % 100 == 0:
                        logger.info(f"下载进度: {percent:.1f}%")
            
            urllib.request.urlretrieve(url, temp_dest, reporthook=report_progress)
            
            # 下载完成，重命名文件
            os.rename(temp_dest, dest)
            file_size = os.path.getsize(dest)
            logger.info(f"下载完成: {dest}，大小: {file_size / (1024*1024):.2f} MB")
            return True
        except Exception as e:
            logger.error(f"下载失败 ({attempt+1}/{max_retries}): {e}")
            
            # 最后一次尝试失败，打印详细错误
            if attempt == max_retries - 1:
                logger.error(f"详细错误: {traceback.format_exc()}")
                # 清理临时文件
                if os.path.exists(temp_dest):
                    try:
                        os.remove(temp_dest)
                    except:
                        pass
                return False
                
            # 等待一段时间后重试
            wait_time = 2 * (attempt + 1)  # 指数退避
            logger.info(f"等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)
    
    return False

def download_model(model_name, model_dir):
    """下载指定的模型"""
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    
    if model_name not in MODEL_URLS:
        logger.error(f"未知模型: {model_name}，可用模型: {', '.join(MODEL_URLS.keys())}")
        return False
        
    model_url = MODEL_URLS[model_name]
    model_path = model_dir / f"{model_name}.pt"
    
    logger.info(f"准备下载 {model_name} 模型...")
    return download_with_retry(model_url, str(model_path))

def check_model_exists(model_name, model_dir):
    """检查模型文件是否已存在"""
    model_path = Path(model_dir) / f"{model_name}.pt"
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        logger.info(f"模型 {model_name} 已存在，大小: {size_mb:.2f} MB")
        return True
    return False

def download_models(models, model_dir):
    """下载指定的所有模型"""
    results = {}
    
    for model_name in models:
        if check_model_exists(model_name, model_dir):
            results[model_name] = "已存在"
            continue
            
        logger.info(f"开始下载 {model_name} 模型...")
        success = download_model(model_name, model_dir)
        results[model_name] = "成功" if success else "失败"
    
    return results

def test_model_loading(model_name, model_dir):
    """测试模型是否可以成功加载"""
    try:
        logger.info(f"测试加载 {model_name} 模型...")
        model = whisper.load_model(model_name, download_root=str(model_dir))
        logger.info(f"{model_name} 模型加载成功")
        return True
    except Exception as e:
        logger.error(f"{model_name} 模型加载失败: {e}")
        logger.error(traceback.format_exc())
        return False

def main():
    parser = argparse.ArgumentParser(description="下载Whisper模型")
    parser.add_argument("--models", type=str, default="tiny,base,small,turbo",
                        help="要下载的模型，逗号分隔 (可用: tiny, base, small, medium, large, turbo)")
    parser.add_argument("--dir", type=str, default="models/whisper",
                        help="模型存储目录")
    parser.add_argument("--test", action="store_true",
                        help="下载后测试模型加载")
    args = parser.parse_args()
    
    model_names = [m.strip() for m in args.models.split(",")]
    model_dir = args.dir
    
    logger.info(f"将下载以下模型到 {model_dir}: {', '.join(model_names)}")
    
    # 检查并创建模型目录
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    
    # 下载模型
    results = download_models(model_names, model_dir)
    
    # 显示结果
    logger.info("\n下载结果:")
    for model, status in results.items():
        logger.info(f"{model}: {status}")
    
    # 测试模型加载
    if args.test:
        logger.info("\n测试模型加载:")
        for model in model_names:
            if results[model] in ["成功", "已存在"]:
                success = test_model_loading(model, model_dir)
                logger.info(f"{model} 模型加载测试: {'成功' if success else '失败'}")

if __name__ == "__main__":
    main() 