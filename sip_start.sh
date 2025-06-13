
LOG_FILE="/home/user/chatp/sip_start.log"  # 可选日志文件
cd /home/user/chatp
#sed -i 's/778778/006006/g' ./conf/config9*.yaml
#sed -i 's/response98/response098_006/g' ./conf/config9*.yaml
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
    # for config in 158 159 160 161 162 200 288 950 951 952 953 954 955 956 957 958 959 960 961 962 963 964 965 967 968 969 970 971 972 973 974 975 976 977 978 979 980 981 982 983 984 985; do
    # for config in 158 159 160 161 162 200 288 950 951 952 953 954 955 956 957 958 959 960 961 962 963 964 965 967 968 969 970 971 972 973; do
    for config in 158 159 160 161 162 200 288 950 951 952 953 954 955 956 957 958 959 960 961 962; do
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

# 生成语音文件
# nohup python3 main.py ./conf/config158.yaml > 158.log 2>&1 &
# nohup python3 main.py ./conf/config200.yaml > 200.log 2>&1 &
# nohup python3 main.py ./conf/config288.yaml > 288.log 2>&1 &
# nohup python3 main.py ./conf/config950.yaml > 950.log 2>&1 &
# nohup python3 main.py ./conf/config999.yaml > 999.log 2>&1 &