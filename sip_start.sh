
LOG_FILE="/home/user/chatp/sip_start.log"  # 可选日志文件
cd /home/user/chatp
sleep 20
# 监控进程并自动重启
while true; do
    # 检查 whisper_main.py 进程
    if ! pgrep -f "python3 whisper_main.py" > /dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') whisper_main.py 正在启动..." >> "$LOG_FILE"
        nohup python3 whisper_main.py > 000.log 2>&1 &
        sleep 30
    fi

    # 检查所有 main.py 进程
    for config in 981 982 983 984 985 158 200 288 388; do
        if ! pgrep -f "python3 main.py ./conf/config${config}.yaml" > /dev/null; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') config${config}.yaml 正在启动..." >> "$LOG_FILE"
            nohup python3 main.py ./conf/config${config}.yaml > ${config}.log 2>&1 &
            sleep 3
        fi
    done

    # 每60秒检查一次
    sleep 60
done