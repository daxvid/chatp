cd /home/user/chatp
sleep 3
# 检查所有 main.py 进程
for config in 981 982 983 984 985 986 987 988 989 990 991 992 993 994 158 159 160 161 162 163 164 165 166 167 168 169 200 201 202 288 289 290 388; do
    if ! pgrep -f "python3 main.py ./conf/config${config}.yaml" > /dev/null; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') config${config}.yaml 正在启动..." >> "$LOG_FILE"
            nohup python3 main.py ./conf/config${config}.yaml > ${config}.log 2>&1 &
            sleep 3
    fi
done