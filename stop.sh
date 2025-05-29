ps -aux|grep main.py
pgrep -f 'python3 main.py ./conf/config.*\.yaml' | xargs kill
ps -aux|grep main.py
