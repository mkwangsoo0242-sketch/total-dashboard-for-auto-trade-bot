# 🤖 트레이딩 봇 통합 USB 설치 가이드

이 폴더는 다른 컴퓨터에 봇을 쉽게 설치하고 실행하기 위해 준비되었습니다.

## 📁 구성 요소

1. **bots/**: 공통 라이브러리 폴더
2. **BTC_30분봉_Live/**: 비트코인 30분봉 자동매매 봇
3. **bybit_bot_usb(1시간-통합)/**: 바이비트 1시간봉 봇 및 대시보드
4. **deploy_package--15분봉/**: 15분봉 봇 패키지
5. **RealTradingBot_Deployment(5분봉)/**: 5분봉 실거래 봇 및 대시보드
6. **docker-compose.yml**: 전체 봇 통합 실행 설정 파일
7. **install.sh**: 원클릭 설치 스크립트

## 🚀 설치 및 실행 방법 (새 컴퓨터에서)

### 1단계: 폴더 이동

USB를 꽂고 이 `usb_deployment` 폴더를 컴퓨터 원하는 곳으로 복사하세요.
터미널을 열고 해당 폴더로 이동합니다.

```bash
cd /경로/usb_deployment
```

(예: 바탕화면에 복사했다면 `cd ~/Desktop/usb_deployment`)

### 2단계: 설치 및 실행

`install.sh` 스크립트를 실행하면 Docker 설치부터 봇 실행까지 자동으로 수행됩니다.

```bash
# 실행 권한 부여
chmod +x install.sh

# 설치 스크립트 실행 (비밀번호 입력 필요)
./install.sh
```

### 3단계: 확인

설치가 완료되면 다음 명령어로 봇들이 정상적으로 동작하는지 확인하세요.

```bash
sudo docker-compose ps
```

### 4단계: 대시보드 접속

웹 브라우저를 열고 다음 주소로 접속하여 봇 상태를 확인하세요.

- **바이비트 1시간 봇**: [http://localhost:5000](http://localhost:5000)
- **실거래 5분봉 봇**: [http://localhost:5001](http://localhost:5001)

## ⚠️ 주의사항

- 인터넷이 연결되어 있어야 합니다 (Docker 설치 및 라이브러리 다운로드).
- 우분투(Linux) 환경을 기준으로 작성되었습니다. Windows의 경우 Docker Desktop을 설치한 후 `docker-compose up -d --build`를 직접 실행하세요.
