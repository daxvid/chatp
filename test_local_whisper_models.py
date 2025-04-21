import whisper
import time
import os
import logging
from pathlib import Path
import traceback
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
    # 显示GPU内存信息
    gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    logger.info(f"GPU内存: {gpu_memory:.2f} GB")

def find_local_models(model_dir):
    """查找本地已有的Whisper模型"""
    model_dir = Path(model_dir)
    if not model_dir.exists():
        return []
    
    local_models = []
    for model_name in ["tiny", "base", "small", "turbo"]:
        model_path = model_dir / f"{model_name}.pt"
        if model_path.exists():
            local_models.append(model_name)
            logger.info(f"找到本地模型: {model_name}")
    
    return local_models

def main():
    """测试本地已有的Whisper模型的转录性能"""
    # 测试音频文件
    audio_file = "recordings/test.wav"
    
    # 检查音频文件是否存在
    if not os.path.exists(audio_file):
        logger.error(f"测试音频文件不存在: {audio_file}")
        return
    
    # 模型目录
    model_dir = "models/whisper"
    
    # 查找本地模型
    local_models = find_local_models(model_dir)
    
    if not local_models:
        logger.error("没有找到本地模型，请先下载模型或确保模型路径正确")
        return
    
    logger.info(f"找到 {len(local_models)} 个本地模型: {', '.join(local_models)}")
    
    # 存储结果
    results = []
    
    # 先加载所有模型
    loaded_models = {}
    for model_name in local_models:
        try:
            logger.info(f"加载 {model_name} 模型...")
            model = whisper.load_model(model_name, device=DEVICE, download_root=model_dir)
            loaded_models[model_name] = model
            logger.info(f"{model_name} 模型加载成功")
        except Exception as e:
            logger.error(f"加载 {model_name} 模型失败: {e}")
            logger.error(traceback.format_exc())
    
    if not loaded_models:
        logger.error("没有成功加载任何模型，测试终止")
        return
    
    # 测试各模型的转录性能
    for model_name, model in loaded_models.items():
        logger.info(f"\n测试 {model_name} 模型转录性能...")
        
        try:
            # 预热GPU（如果使用GPU）
            if DEVICE == "cuda":
                logger.info(f"GPU预热...")
                # 简单运行一个小的转录任务预热GPU
                _ = model.transcribe(audio_file, language="zh", fp16=True, duration=1.0)
                torch.cuda.synchronize()  # 确保预热完成
                logger.info(f"GPU预热完成")
            
            # 清理缓存
            if DEVICE == "cuda":
                torch.cuda.empty_cache()
                
            # 只测量转录时间
            transcribe_start = time.time()
            result = model.transcribe(
                audio_file,
                language="zh",
                fp16=True  # 启用半精度浮点数加速
            )
            # 确保GPU操作完成
            if DEVICE == "cuda":
                torch.cuda.synchronize()
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
            logger.error(traceback.format_exc())
    
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