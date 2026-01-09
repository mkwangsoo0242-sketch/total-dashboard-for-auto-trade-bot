# 🚀 통합 트레이딩 봇 배포 가이드

## 📦 패키지 내용

이 배포 패키지에는 다음이 포함되어 있습니다:

### 봇 디렉토리

- **Real_5m/** - 5분봉 트레이딩 봇 (ML 기반)
- **Deploy_15m/** - 15분봉 트레이딩 봇 (LightGBM)
- **BTC_30m/** - 30분봉 트레이딩 봇 (Adaptive Strategy)
- **Bybit_1h/** - 1시간봉 트레이딩 봇 (XGBoost)

### 대시보드

- **dashboard/** - 통합 관리 대시보드
  - `bot_manager.py` - 메인 서버
  - `templates/` - 웹 인터페이스
  - `bots/` - 봇 기본 클래스

### 설정 파일

- `.env.example` - 환경 변수 템플릿
- `requirements.txt` - Python 의존성
- `docker-compose.yml` - Docker 설정
- `setup.sh` - 자동 설치 스크립트
- `start.sh` - 시작 스크립트

---

## 🔧 서버 설치 방법

### 1단계: 파일 전송

```bash
# 압축 파일을 서버로 전송
scp usb_deployment_*.tar.gz user@server:/home/user/

# 서버에 SSH 접속
ssh user@server

# 압축 해제
cd /home/user
tar -xzf usb_deployment_*.tar.gz
cd usb_deployment
```

### 2단계: 환경 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집
nano .env
```

**필수 환경 변수:**

```env
# 트레이딩 모드
TRADING_MODE=paper  # paper 또는 real

# Binance API (5분봉, 30분봉용)
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET=your_binance_secret

# Bybit API (1시간봉용)
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_secret

# 심볼
SYMBOL=BTC/USDT
```

### 3단계: Docker로 설치 (권장)

```bash
# 설치 스크립트 실행 (Docker, Docker Compose 자동 설치)
chmod +x setup.sh
./setup.sh

# 시작
chmod +x start.sh
./start.sh
```

### 3단계 (대안): 수동 설치

```bash
# Python 3.10+ 필요
python3 --version

# 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 대시보드 실행
cd dashboard
python bot_manager.py
```

---

## 📊 대시보드 사용법

### 접속

- URL: `http://서버IP:8000`
- 로컬: `http://localhost:8000`

### 주요 기능

#### 1. 봇 상태 모니터링

- **상태 색상:**
  - 🔵 파란색: 신호 대기 중
  - 🟢 녹색: 롱 포지션 보유
  - 🔴 빨간색: 숏 포지션 보유
  - ⚪ 회색: 정지됨
  - 🟠 주황색: 오류

#### 2. Start/Stop 제어

- **Start 버튼:** 정지된 봇을 시작
- **Stop 버튼:** 실행 중인 봇을 정지
- 버튼은 상태에 따라 자동으로 활성화/비활성화됩니다

#### 3. 마지막 업데이트

- 실행 중인 봇: 시간이 계속 갱신됨
- 정지된 봇: `-` 표시
- 업데이트가 멈추면 봇에 문제가 있을 수 있습니다

#### 4. 실시간 차트

- 각 봇의 가격 차트 (캔들스틱)
- Entry, Stop Loss, Liquidation 가격 표시
- 전체 자산 추이 그래프

---

## 🔍 문제 해결

### 봇이 시작되지 않을 때

```bash
# 로그 확인
tail -f dashboard/manager.log

# 개별 봇 로그 확인
tail -f Real_5m/bot.log
tail -f Deploy_15m/bot.log
tail -f BTC_30m/bot.log
tail -f Bybit_1h/bot.log
```

### 포트 충돌 시

```bash
# docker-compose.yml 편집
nano docker-compose.yml

# ports 섹션 수정
ports:
  - "8001:8000"  # 8000 대신 8001 사용
```

### API 연결 오류

```bash
# .env 파일 확인
cat .env

# API 키가 올바른지 확인
# 공백이나 특수문자가 없는지 확인
```

### 메모리 부족

```bash
# 일부 봇만 실행
# dashboard/bot_manager.py에서 불필요한 봇 주석 처리
```

---

## 📝 주요 명령어

### Docker 사용 시

```bash
# 시작
./start.sh

# 정지
docker-compose down

# 재시작
docker-compose restart

# 로그 확인
docker-compose logs -f dashboard

# 상태 확인
docker-compose ps
```

### 수동 실행 시

```bash
# 시작
cd dashboard
source ../venv/bin/activate
python bot_manager.py &

# 정지
pkill -f bot_manager.py

# 로그 확인
tail -f manager.log
```

---

## ⚙️ 고급 설정

### 봇 개별 설정

각 봇 디렉토리의 `.env` 또는 `config.json` 파일을 수정하여 개별 설정 가능:

- **Real_5m/.env** - 5분봉 봇 설정
- **Deploy_15m/config.json** - 15분봉 봇 설정
- **BTC_30m/.env** - 30분봉 봇 설정
- **Bybit_1h/config.py** - 1시간봉 봇 설정

### 자동 재학습

- **5분봉 봇:** 매일 00:00 자동 재학습
- **15분봉 봇:** `retrain.py` 수동 실행
- **1시간봉 봇:** 동적 파라미터 최적화 (자동)

---

## 🔐 보안 권장사항

1. **API 키 보안**
   - `.env` 파일 권한: `chmod 600 .env`
   - Git에 커밋하지 않기

2. **방화벽 설정**

   ```bash
   # 대시보드 포트만 허용
   sudo ufw allow 8000/tcp
   ```

3. **HTTPS 설정** (프로덕션 환경)
   - Nginx 리버스 프록시 사용
   - Let's Encrypt SSL 인증서

---

## 📞 지원

### 로그 파일 위치

- 대시보드: `dashboard/manager.log`
- 5분봉: `Real_5m/bot.log`
- 15분봉: `Deploy_15m/bot.log`
- 30분봉: `BTC_30m/bot.log`
- 1시간봉: `Bybit_1h/bot.log`

### 시스템 요구사항

- **OS:** Ubuntu 20.04+ / Debian 11+
- **Python:** 3.10+
- **RAM:** 최소 4GB (권장 8GB)
- **디스크:** 최소 10GB
- **네트워크:** 안정적인 인터넷 연결

---

## 📈 성능 모니터링

```bash
# CPU/메모리 사용량 확인
htop

# 디스크 사용량
df -h

# 네트워크 상태
netstat -tuln | grep 8000
```

---

## 🎯 다음 단계

1. ✅ 서버에 배포 완료
2. ✅ .env 파일 설정
3. ✅ Docker로 실행
4. ✅ 대시보드 접속 확인
5. ⏭️ Paper Trading으로 테스트
6. ⏭️ Real Trading 전환 (신중하게!)

**주의:** Real Trading으로 전환하기 전에 반드시 Paper Trading으로 충분히 테스트하세요!
