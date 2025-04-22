#!/bin/bash

# 设置虚拟音频设备，用于在无声卡环境中运行SIP应用
# 这个脚本需要以root或sudoer权限运行

echo "设置虚拟音频环境..."

# 检查是否安装了PulseAudio
if ! command -v pulseaudio &> /dev/null; then
    echo "正在安装PulseAudio..."
    apt-get update
    apt-get install -y pulseaudio pulseaudio-utils
fi

# 检查是否有ALSA工具
if ! command -v aplay &> /dev/null; then
    echo "正在安装ALSA工具..."
    apt-get install -y alsa-utils
fi

# 确保PulseAudio服务已停止(防止已有的会话干扰)
pulseaudio --kill 2>/dev/null

# 等待PulseAudio完全关闭
sleep 2

# 启动PulseAudio守护程序
echo "启动PulseAudio..."
pulseaudio --start --log-target=syslog

# 等待PulseAudio启动
sleep 2

# 加载虚拟音频设备模块
echo "加载虚拟音频设备..."
pactl load-module module-null-sink sink_name=virtual_speaker
pactl load-module module-virtual-source source_name=virtual_mic

# 显示当前可用的音频设备
echo "当前可用的声音输出设备:"
pactl list sinks short

echo "当前可用的声音输入设备:"
pactl list sources short

echo "虚拟音频环境设置完成。"
echo "您现在可以运行SIP应用而不需要物理音频设备。"
echo "使用 'pulseaudio --kill' 可以停止PulseAudio服务。" 