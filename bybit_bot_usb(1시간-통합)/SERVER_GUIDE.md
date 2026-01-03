# 우분투 서버 구축 및 Trae SSH 연결 가이드

## 1. 우분투 서버 필수 설정
우분투 설치 후 터미널에서 아래 명령어를 순서대로 실행하세요.

```bash
# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# SSH 서버 설치 및 확인
sudo apt install openssh-server -y
sudo systemctl enable --now ssh

# 파이썬 및 필수 도구 설치
sudo apt install python3-pip python3-venv git -y

# (선택) PM2 설치를 위한 Node.js 설치
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install pm2 -g
```

## 2. 방화벽 및 네트워크 (외부 접속용)
- **SSH**: `sudo ufw allow 22`
- **대시보드**: `sudo ufw allow 5000` (웹 모니터링용)
- **공유기 설정**: 공유기 관리 페이지에서 **포트 포워딩(Port Forwarding)** 설정을 찾아 외부 포트 22를 서버의 내부 IP 22번으로 연결하세요.

## 3. Trae에서 접속 방법
1. Trae 실행 -> `Ctrl + Shift + P` -> `Remote-SSH: Connect to Host...`
2. `Add New SSH Host...` 선택
3. `ssh 계정명@서버외부IP` 입력
4. 접속 후 `Open Folder`를 눌러 USB에서 복사해온 `bybit_bot_usb` 폴더를 선택하세요.

## 4. 봇 실행 (PM2 기준)
```bash
cd bybit_bot_usb
pip install -r requirements.txt
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```
