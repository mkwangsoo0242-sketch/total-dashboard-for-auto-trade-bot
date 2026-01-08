# 🤖 트레이딩 봇 통합 USB (Docker 버전)

이 폴더는 **Docker**를 사용하여 모든 트레이딩 봇을 한 번에 설치하고, **컴퓨터 전원이 켜지면 자동으로 실행**되도록 구성되어 있습니다.

## 📁 폴더 구성

- **BTC_30m/**: 비트코인 30분봉 봇
- **Bybit_1h/**: 바이비트 1시간봉 봇
- **Deploy_15m/**: 15분봉 봇
- **Real_5m/**: 실거래 5분봉 봇
- **docker-compose.yml**: 통합 실행 설정 파일
- **install.sh**: 원클릭 설치/실행 스크립트

## 🚀 새 컴퓨터 설치 방법

1. `usb_deployment` 폴더 전체를 새 컴퓨터로 복사합니다.
2. 터미널을 열고 폴더로 이동합니다.

   ```bash
   cd /경로/usb_deployment
   ```

3. 설치 스크립트를 실행합니다. (인터넷 연결 필수)

   ```bash
   chmod +x install.sh
   ./install.sh
   ```

   *비밀번호를 물어보면 입력하세요.*

## ✅ 설치 후 동작

- 스크립트가 Docker를 설치하고, 4개의 봇을 즉시 실행합니다.
- `restart: always` 설정이 적용되어 있어, **컴퓨터를 재부팅해도 봇이 자동으로 다시 켜집니다.**
- **따로 설정을 만질 필요가 없습니다.**

## 🛠 관리 명령어

터미널에서 `usb_deployment` 폴더로 이동한 후 사용하세요.

- **상태 확인**: `sudo docker-compose ps`
- **로그 보기**: `sudo docker-compose logs -f` (나가기는 `Ctrl+C`)
- **봇 끄기**: `sudo docker-compose down`
- **봇 켜기/업데이트**: `sudo docker-compose up -d --build`

## 📊 대시보드 (웹)

봇이 실행 중일 때 브라우저에서 볼 수 있습니다.

- Bybit 1시간 봇: <http://localhost:5000>
- 실거래 5분 봇: <http://localhost:5001>
