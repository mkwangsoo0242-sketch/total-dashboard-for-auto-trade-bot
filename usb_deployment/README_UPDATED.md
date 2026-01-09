# 통합 트레이딩 봇 배포 패키지

## 📦 포함된 봇

1. **Bot_5M** (5분봉) - Real_5m/
2. **Bot_15M** (15분봉) - Deploy_15m/
3. **Bot_30M** (30분봉) - BTC_30m/
4. **Bot_1H** (1시간봉) - Bybit_1h/

## 🚀 빠른 시작

### 1. 환경 설정
```bash
# .env 파일 생성
cp .env.example .env
# .env 파일을 편집하여 API 키 입력
nano .env
```

### 2. Docker로 실행 (권장)
```bash
# 설치 스크립트 실행
chmod +x setup.sh
./setup.sh

# 시작
chmod +x start.sh
./start.sh
```

### 3. 수동 실행
```bash
# Python 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 대시보드 실행
cd dashboard
python bot_manager.py
```

## 📊 대시보드 접속

- URL: http://localhost:8000
- 기능:
  - 실시간 봇 상태 모니터링
  - 개별 봇 Start/Stop 제어
  - 마지막 업데이트 시간 확인
  - 자산 추이 차트

## ⚙️ 주요 기능

### Start/Stop 버튼
- 각 봇을 개별적으로 시작/정지 가능
- 실행 중인 봇은 Stop 버튼만 활성화
- 정지된 봇은 Start 버튼만 활성화

### 마지막 업데이트
- 봇이 실행 중이면 시간이 계속 갱신
- 봇이 정지되면 '-' 표시

### 상태 색상
- 파란색: 신호 대기 중
- 녹색/빨간색: 포지션 보유 중
- 회색: 정지됨
- 주황색: 오류

## 📝 환경 변수

필수 환경 변수 (.env 파일):
```
TRADING_MODE=paper  # paper 또는 real
BINANCE_API_KEY=your_key
BINANCE_SECRET=your_secret
BYBIT_API_KEY=your_key
BYBIT_API_SECRET=your_secret
```

## 🔧 문제 해결

### 봇이 시작되지 않을 때
```bash
# 로그 확인
tail -f dashboard/manager.log
```

### 포트 충돌 시
```bash
# docker-compose.yml에서 포트 변경
ports:
  - "8001:8000"  # 8000 대신 8001 사용
```

## 📞 지원

문제가 발생하면 로그 파일을 확인하세요:
- dashboard/manager.log
- Real_5m/*.log
- Deploy_15m/*.log
- BTC_30m/*.log
- Bybit_1h/*.log
