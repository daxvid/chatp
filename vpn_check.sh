#!/bin/bash

# 配置参数
TARGET_IP="119.12.161.38"            # 替换为你的目标 IP
CHECK_INTERVAL=3               # 检查间隔（秒）
OVPN_PROCESS="/usr/sbin/openvpn"
LOG_FILE="/var/log/ovpn_watchdog.log"  # 可选日志文件

# 初始化计数器（可选）
counter=0
sleep 60
while true; do
  # 获取当前外部 IPv4（使用多个服务确保可靠性）
  CURRENT_IP=$(curl -4 -s --max-time 5 api.ipify.org || curl -4 -s --max-time 5 ifconfig.me)
  
  # 记录日志（可选）
  timestamp=$(date "+%Y-%m-%d %H:%M:%S")
  echo "[$timestamp] Current IP: $CURRENT_IP" >> "$LOG_FILE"

  # 核心检查逻辑
  if [ "$CURRENT_IP" != "$TARGET_IP" ]; then
    echo "IP mismatch detected! Expected $TARGET_IP, got $CURRENT_IP" >> "$LOG_FILE"
    
    # 终止 OpenVPN 进程
    if pgrep -x "$(basename "$OVPN_PROCESS")" >/dev/null; then
      echo "Killing existing OpenVPN process..." >> "$LOG_FILE"
      sudo pkill -f "$OVPN_PROCESS"
      sleep 2  # 等待进程终止
    fi

    # 启动新进程
    echo "Restarting OpenVPN..." >> "$LOG_FILE"
    sudo nohup $OVPN_PROCESS --suppress-timestamps --nobind --config /etc/openvpn/client/a.conf > /var/log/openvpn.log 2>&1 &
    sleep 60
    counter=$((counter+1))
    # 可选：防止频繁重启（每小时最多 10 次）
    if [ $counter -ge 10000 ]; then
      echo "Restart limit reached. Exiting." >> "$LOG_FILE"
      exit 1
    fi
  else
    counter=0  # 重置计数器
  fi

  sleep $CHECK_INTERVAL
done
