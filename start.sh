cd /home/user/chatp
sleep 60
nohup python3 whisper_main.py > 000.log 2>&1 &
sleep 3
nohup python3 main.py ./conf/config981.yaml > 981.log 2>&1 &
sleep 3
nohup python3 main.py ./conf/config982.yaml > 982.log 2>&1 &
sleep 3
nohup python3 main.py ./conf/config983.yaml > 983.log 2>&1 &
sleep 3
nohup python3 main.py ./conf/config984.yaml > 984.log 2>&1 &
sleep 3
nohup python3 main.py ./conf/config985.yaml > 985.log 2>&1 &
sleep 3
nohup python3 main.py ./conf/config158.yaml > 158.log 2>&1 &
sleep 3
nohup python3 main.py ./conf/config200.yaml > 200.log 2>&1 &
sleep 3
nohup python3 main.py ./conf/config288.yaml > 288.log 2>&1 &
sleep 3
nohup python3 main.py ./conf/config388.yaml > 388.log 2>&1 &


# sudo nohup /usr/sbin/openvpn --suppress-timestamps --nobind --config /etc/openvpn/client/a.conf > vpn.log 2>&1 &