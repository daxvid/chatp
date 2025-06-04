LOG_FILE="/home/user/chatp/sip_start.log"  # 可选日志文件
cd /home/user/chatp
sleep 3
# 检查所有 main.py 进程
for config in 950 158 200 288; do
    if ! pgrep -f "python3 main.py ./conf/config${config}.yaml" > /dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') config${config}.yaml 正在启动..." >> "$LOG_FILE"
        nohup python3 main.py ./conf/config${config}.yaml > ${config}.log 2>&1 &
        sleep 3
    fi
done
