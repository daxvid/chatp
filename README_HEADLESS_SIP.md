# 在无声卡环境中运行SIP应用

这个文档解释如何在没有物理音频设备（如无头服务器、Docker容器或虚拟机）的环境中运行SIP应用。

## 问题描述

当尝试在没有物理音频设备的环境中运行基于PJSIP的应用时，可能会遇到以下错误：

```
Error retrieving default audio device parameters: Unable to find default audio device (PJMEDIA_EAUD_NODEFDEV) [status=420006]
```

这是因为PJSIP库尝试查找并使用默认的音频设备，但在没有声卡的环境中无法找到这些设备。

## 解决方案

### 方案1: 使用虚拟音频设备

我们可以通过配置虚拟音频设备来解决这个问题。这种方法使用PulseAudio创建虚拟的输入和输出设备，使PJSIP能够正常工作。

#### 步骤：

1. 安装必要的软件包：

```bash
sudo apt-get update
sudo apt-get install -y pulseaudio pulseaudio-utils alsa-utils
```

2. 运行提供的脚本设置虚拟音频设备：

```bash
chmod +x setup_virtual_audio.sh
sudo ./setup_virtual_audio.sh
```

3. 确认虚拟设备已创建：

```bash
pactl list sinks short
pactl list sources short
```

这些命令应该会显示名为"virtual_speaker"和"virtual_mic"的设备。

4. 现在可以运行SIP应用了。

### 方案2: 修改代码以支持无声卡环境

我们已经修改了`SIPCaller`类，使其在初始化时配置为使用空设备（null device），这样即使在没有物理音频设备的环境中也能正常工作。

关键修改包括：

1. 在`EpConfig`中设置`uaConfig.noAudioDevice = True`，允许无音频设备启动

2. 配置音频设备使用null设备：

```python
self.ep.audDevManager().setNullDev()  # 设置空音频设备
```

3. 添加异常处理，确保即使音频设备配置失败，应用也能继续运行

## 在Docker中使用

如果在Docker容器中运行SIP应用，需要特别注意：

1. 在Dockerfile中安装必要的包：

```dockerfile
RUN apt-get update && apt-get install -y \
    pulseaudio \
    pulseaudio-utils \
    alsa-utils
```

2. 在容器启动时运行虚拟音频设置脚本：

```bash
./setup_virtual_audio.sh
```

3. 然后启动SIP应用。

## 调试问题

如果仍然遇到音频设备相关的问题，可以尝试以下调试步骤：

1. 检查PulseAudio是否正在运行：

```bash
pulseaudio --check
```

2. 重启PulseAudio：

```bash
pulseaudio --kill
pulseaudio --start --log-target=syslog
```

3. 检查日志以获取更多信息：

```bash
tail -f /var/log/syslog | grep pulseaudio
```

4. 验证PJSIP是否能够检测到音频设备：

```python
import pjsua2 as pj
ep = pj.Endpoint()
ep.libCreate()
ep.libInit(pj.EpConfig())
print("音频设备数量:", ep.audDevManager().getDevCount())
for i in range(ep.audDevManager().getDevCount()):
    dev_info = ep.audDevManager().getDevInfo(i)
    print(f"设备 {i}: {dev_info.name}")
```

## 注意事项

- 虽然这个设置允许SIP应用在无声卡环境中运行，但由于没有实际的音频硬件，您将无法进行实时的音频捕获或播放
- 这个设置主要适用于使用外部录音/播放机制的应用（如我们的应用使用TTS和Whisper进行语音处理）
- 在某些环境中，可能需要root或sudo权限才能配置PulseAudio 