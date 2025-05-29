
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

    # 检查 tg_bot.py 进程
    if ! pgrep -f "python3 tg_bot.py" > /dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') tg_bot.py 正在启动..." >> "$LOG_FILE"
        nohup python3 tg_bot.py > 001.log 2>&1 &
        sleep 30
    fi

    # 检查所有 main.py 进程
    for config in 967 968 969 970 971 972 973 974 975 976 977 978 979 980 981 982 983 984 985 986 987 988 989 990 991 992 993 994 995 996 997 998 999 158 159 160 161 162 163 164 165 166 167 168 169 200 201 202 288 290; do
        if ! pgrep -f "python3 main.py ./conf/config${config}.yaml" > /dev/null; then
            # 检查config${config}.yaml是否存在
            if [ ! -f ./conf/config${config}.yaml ]; then
                continue
            fi
            # tel${config}.txt是否存在
            if [ ! -f ./conf/tel${config}.txt ]; then
                continue
            fi
            echo "$(date '+%Y-%m-%d %H:%M:%S') config${config}.yaml 正在启动..." >> "$LOG_FILE"
            nohup python3 main.py ./conf/config${config}.yaml > ${config}.log 2>&1 &
            sleep 3
        fi
    done

    # 每60秒检查一次
    sleep 60
done