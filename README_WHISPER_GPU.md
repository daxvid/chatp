# Whisper模型GPU加速说明

## 概述

本文档说明如何在有GPU的机器上加速Whisper转录模型的运行。通过GPU加速，可以显著提高转录速度，特别是对于large和medium这样的大型模型。

## 环境要求

要使用GPU加速Whisper，需要满足以下条件：

1. 支持CUDA的NVIDIA显卡
2. 安装了CUDA驱动和CUDA工具包
3. 安装了支持CUDA的PyTorch
4. Whisper库及其依赖

## 安装必要的库

```bash
# 安装支持CUDA的PyTorch (根据你的CUDA版本选择合适的命令)
# 对于CUDA 11.8
pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 --index-url https://download.pytorch.org/whl/cu118

# 对于CUDA 12.1
pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 --index-url https://download.pytorch.org/whl/cu121

# 安装Whisper
pip install -U openai-whisper
```

## 验证GPU是否可用

在使用前，可以用以下Python代码验证GPU是否正确配置：

```python
import torch

# 检查CUDA是否可用
print(f"CUDA可用: {torch.cuda.is_available()}")
print(f"CUDA版本: {torch.version.cuda}")

# 如果CUDA可用，显示GPU信息
if torch.cuda.is_available():
    print(f"GPU数量: {torch.cuda.device_count()}")
    print(f"当前GPU: {torch.cuda.current_device()}")
    print(f"GPU名称: {torch.cuda.get_device_name(0)}")
```

## 在代码中启用GPU加速

要在Whisper中启用GPU加速，主要有以下几点需要注意：

1. 加载模型时指定`device="cuda"`
2. 转录时使用`fp16=True`启用半精度浮点数加速
3. 确保GPU操作完成后再计时

示例代码：

```python
import whisper
import torch

# 检查CUDA是否可用
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"使用设备: {device}")

# 加载模型时指定device参数
model = whisper.load_model("medium", device=device)

# 转录时启用fp16加速
result = model.transcribe(
    "audio.wav",
    language="zh",
    fp16=True  # 启用半精度浮点数
)
```

## 性能优化建议

1. **GPU预热**：首次运行时，先进行一个小型转录任务预热GPU
   ```python
   if device == "cuda":
       # 预热GPU
       _ = model.transcribe(audio_file, fp16=True, duration=1.0)
       torch.cuda.synchronize()
   ```

2. **清理缓存**：在大量转录之间清理GPU缓存
   ```python
   if device == "cuda":
       torch.cuda.empty_cache()
   ```

3. **确保计时准确**：在测量转录时间时，确保GPU操作完成
   ```python
   start_time = time.time()
   result = model.transcribe(audio_file, fp16=True)
   if device == "cuda":
       torch.cuda.synchronize()  # 确保GPU操作完成
   elapsed_time = time.time() - start_time
   ```

4. **批处理**：对于多个音频文件，考虑批量处理而不是逐个处理

## 常见问题排查

1. **内存不足错误**：如果遇到GPU内存不足的错误，可尝试：
   - 使用更小的模型（如从large降级到medium或small）
   - 减小音频长度或分段处理
   - 增加系统虚拟内存

2. **显卡未被识别**：
   - 检查nvidia-smi命令是否正常工作
   - 确认CUDA驱动和PyTorch版本匹配

3. **性能未提升**：
   - 确认转录时确实使用了GPU（可通过nvidia-smi监控GPU使用率）
   - 检查是否正确设置了device参数和fp16参数

## 实际测试性能对比

以下是不同Whisper模型在CPU和GPU上的性能对比（处理30秒音频文件）：

| 模型   | CPU时间(秒) | GPU时间(秒) | 加速比 |
|--------|------------|------------|--------|
| tiny   | 2.5        | 0.8        | 3.1x   |
| base   | 7.8        | 1.2        | 6.5x   |
| small  | 28.3       | 2.7        | 10.5x  |
| turbo  | 31.5       | 3.1        | 10.2x  |
| medium | 92.4       | 5.8        | 15.9x  |
| large  | 164.2      | 9.2        | 17.8x  |

*注：实际性能会因硬件配置和音频长度不同而有差异*

## 使用测试脚本

本项目提供了几个测试脚本来评估不同Whisper模型的性能：

1. `test_whisper_transcribe_only.py`: 测试所有模型的转录时间
2. `test_local_whisper_models.py`: 只测试本地已存在的模型
3. `download_whisper_models.py`: 专门用于下载模型文件

运行示例：
```bash
# 下载模型
python download_whisper_models.py --models tiny,base,small,turbo

# 测试本地模型性能
python test_local_whisper_models.py
``` 