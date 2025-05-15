ps -aux|grep main.py
pgrep -f 'python3 main.py ./conf/config.*\.yaml' | xargs kill
sleep 30
ps -aux|grep main.py

