# 自动电话呼叫系统

这个项目是一个基于Python的自动电话呼叫系统，能够批量拨打电话，播放合成的语音，并录制通话内容。

## 功能特点

- 批量拨打电话列表
- 文本转语音（使用edge-tts）
- 播放预设的语音文件（支持MP3和WAV格式）
- 录制通话音频并保存
- 使用Whisper进行语音识别
- 记录呼叫结果和通话内容

## 系统要求

- Python 3.8+
- PJSIP/PJSUA2 库
- FFmpeg（用于音频转换）
- 互联网连接（用于下载模型）

## 安装

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/auto-caller.git
cd auto-caller
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 安装FFmpeg：
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg
```

## 配置

编辑`config.yaml`文件，设置以下参数：

```yaml
sip:
  server: "your.sip.server"      # SIP服务器地址
  port: 62060                    # SIP服务器端口
  username: "your_username"      # SIP账户用户名
  password: "your_password"      # SIP账户密码
  bind_port: 5060                # 本地绑定端口
  tts_text: "您好，这是一个自动语音通知..." # 要播放的文本
  tts_voice: "zh-CN-XiaoxiaoNeural" # 语音合成声音

call:
  list_file: "tel.txt"           # 电话号码列表
  log_file: "call_log.csv"       # 呼叫记录日志
  interval: 5                    # 两次呼叫间隔(秒)

whisper:
  model_size: "small"            # Whisper模型大小
  model_dir: "models/whisper"    # 模型保存目录
```

## 使用方法

1. 准备电话号码列表：
   - 创建`tel.txt`文件，每行一个电话号码

2. 运行程序：
```bash
# 基本运行方式
python main.py

# 指定语音文件方式
python main.py --voice-file path/to/your/voice.wav

# 指定响应语音文件方式
python main.py --response-file path/to/response.wav
```

3. 查看结果：
   - 录音文件保存在`recordings`目录
   - 呼叫记录保存在`call_log.csv`文件中
   - 日志保存在`auto_caller.log`文件中

## 项目结构

```
auto-caller/
├── main.py                # 主程序入口
├── config_manager.py      # 配置管理模块
├── sip_caller.py          # SIP通话模块
├── tts_manager.py         # 文本转语音模块
├── whisper_manager.py     # 语音识别模块
├── call_manager.py        # 呼叫管理模块
├── config.yaml            # 配置文件
├── tel.txt                # 电话号码列表
├── requirements.txt       # 依赖列表
├── README.md              # 说明文档
├── recordings/            # 录音文件目录
└── models/                # 模型文件目录
    └── whisper/           # Whisper模型目录
```

## 支持的语音

Edge TTS支持多种语言和声音，以下是部分中文语音：

- zh-CN-XiaoxiaoNeural (默认，小女孩声音)
- zh-CN-XiaoyiNeural (成年女性声音)
- zh-CN-YunjianNeural (男性声音)
- zh-CN-liaoning-XiaobeiNeural (辽宁口音)
- zh-CN-shaanxi-XiaoniNeural (陕西口音)

## 注意事项

- 使用前请确保你有合法的SIP账户
- 确保网络连接良好
- 首次运行会下载Whisper和Edge TTS模型
- 文本转语音的结果会缓存在`tts_cache`目录中
- 呼叫时间可能受到网络延迟的影响

## 问题排查

- 如果遇到SSL证书问题，程序已经禁用了证书验证
- 如果遇到SIP连接问题，检查SIP服务器设置和凭据
- 如果Whisper模型下载失败，可以手动下载并放入`models/whisper`目录

## 许可证

MIT License