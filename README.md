# AI 自动电话推广系统

这是一个使用 Python 开发的自动电话推广系统，能够自动拨打电话、播放录音、识别用户语音并做出相应回复。

## 功能特点

- 使用 PJSIP 进行电话呼叫
- 使用 OpenAI Whisper 进行语音识别
- 使用 scikit-learn 进行意图分析
- 使用 Edge-TTS 进行语音合成
- 支持中文对话
- 使用 YAML 配置文件管理设置
- 本地缓存 Whisper 模型

## 安装要求

- Python 3.8 或更高版本
- PJSIP 开发库
- FFmpeg
- 至少 2GB 可用磁盘空间（用于存储 Whisper 模型）

## 安装步骤

1. 安装系统依赖：
```bash
# Ubuntu/Debian
sudo apt-get install libpjsua2-dev ffmpeg

# macOS
brew install pjsip ffmpeg
```

2. 安装 Python 依赖：
```bash
pip install -r requirements.txt
```

3. 配置系统：
编辑 `config.yaml` 文件，填写以下信息：
```yaml
sip:
  account: "your_sip_account@your_domain"  # SIP账户
  server: "your_sip_server"                # SIP服务器地址
  username: "your_username"                # SIP用户名
  password: "your_password"                # SIP密码
  port: 5060                               # SIP端口

call:
  initial_message: "initial_message.wav"   # 初始语音文件
  response_timeout: 5                      # 等待用户响应时间（秒）
  target_number: "sip:target_number@domain" # 目标电话号码

responses:
  greeting: "您好，我是AI助手，很高兴为您服务。"
  interested: "感谢您的兴趣，我们的产品具有以下特点..."
  not_interested: "感谢您的时间，祝您生活愉快。"
  default: "抱歉，我没有听清楚，请您再说一遍。"
```

## 使用方法

1. 准备初始语音文件：
将您的初始推广语音保存为 `initial_message.wav` 文件。

2. 运行程序：
```bash
python auto_caller.py
```

首次运行时，程序会自动下载 Whisper small 模型并保存到 `models/whisper` 目录。后续运行将直接使用本地缓存的模型。

## 配置说明

在 `config.yaml` 文件中可以配置以下参数：

### SIP 配置
- account: SIP 账户
- server: SIP 服务器地址
- username: SIP 用户名
- password: SIP 密码
- port: SIP 端口

### 通话配置
- initial_message: 初始语音文件路径
- response_timeout: 等待用户响应时间（秒）
- target_number: 目标电话号码

### 响应配置
- responses: 各种场景下的响应文本

## 模型说明

系统使用 OpenAI Whisper small 模型进行语音识别：
- 模型大小：约 1.5GB
- 存储位置：`models/whisper/small.pt`
- 首次运行时会自动下载
- 支持中文语音识别

## 注意事项

- 请确保您的 SIP 账户有足够的通话额度
- 建议在测试环境中先进行测试
- 遵守当地电话营销相关法律法规
- 注意保护用户隐私
- 配置文件中的敏感信息（如密码）建议使用环境变量或加密存储
- 确保有足够的磁盘空间存储 Whisper 模型

## 许可证

MIT License 