# 🔑 각 봇마다 다른 API 키 사용 가이드

## 📋 개요

이 배포 패키지는 **각 봇마다 독립적인 API 키**를 사용할 수 있도록 설계되었습니다.

### 🎯 왜 봇마다 다른 키를 사용하나요?

1. **리스크 분산** - 한 계정에 문제가 생겨도 다른 봇은 계속 작동
2. **자금 관리** - 각 봇에 다른 금액 할당 가능
3. **거래소 제한 회피** - API 호출 제한을 분산
4. **전략 분리** - 각 전략을 독립적으로 관리

---

## 🔧 설정 방법

### 1단계: .env 파일 생성

```bash
cd /path/to/usb_deployment
cp .env.example .env
nano .env  # 또는 vim, vi 등
```

### 2단계: 각 봇의 API 키 입력

```bash
# 5분봉 봇 (Binance 계정 1)
BINANCE_API_KEY_5M=your_account1_api_key
BINANCE_SECRET_5M=your_account1_secret

# 15분봉 봇 (Bybit 계정 1)
BYBIT_API_KEY_15M=your_bybit_account1_api_key
BYBIT_API_SECRET_15M=your_bybit_account1_secret

# 30분봉 봇 (Binance 계정 2)
BINANCE_API_KEY_30M=your_account2_api_key
BINANCE_SECRET_30M=your_account2_secret

# 1시간봉 봇 (Bybit 계정 2)
BYBIT_API_KEY_1H=your_bybit_account2_api_key
BYBIT_API_SECRET_1H=your_bybit_account2_secret

# 트레이딩 모드
TRADING_MODE=paper  # 또는 real
```

### 3단계: 권한 설정 (보안)

```bash
chmod 600 .env  # 소유자만 읽기/쓰기 가능
```

---

## 📊 봇별 API 키 매핑

| 봇 이름 | 시간봉 | 거래소 | 환경 변수 | Fallback |
|---------|--------|--------|-----------|----------|
| **Real_5m** | 5분 | Binance | `BINANCE_API_KEY_5M` | `BINANCE_API_KEY` |
| **Deploy_15m** | 15분 | Bybit | `BYBIT_API_KEY_15M` | `BYBIT_API_KEY` |
| **BTC_30m** | 30분 | Binance | `BINANCE_API_KEY_30M` | `BINANCE_API_KEY` |
| **Bybit_1h** | 1시간 | Bybit | `BYBIT_API_KEY_1H` | `BYBIT_API_KEY` |

---

## 🎯 사용 시나리오

### 시나리오 1: 각 봇마다 완전히 다른 계정 사용 (권장)

**목적:** 최대 리스크 분산

```bash
# .env 파일
BINANCE_API_KEY_5M=binance_account1_key
BINANCE_SECRET_5M=binance_account1_secret

BYBIT_API_KEY_15M=bybit_account1_key
BYBIT_API_SECRET_15M=bybit_account1_secret

BINANCE_API_KEY_30M=binance_account2_key
BINANCE_SECRET_30M=binance_account2_secret

BYBIT_API_KEY_1H=bybit_account2_key
BYBIT_API_SECRET_1H=bybit_account2_secret

TRADING_MODE=real
```

**결과:**

- 5분봉 → Binance 계정 1
- 15분봉 → Bybit 계정 1
- 30분봉 → Binance 계정 2
- 1시간봉 → Bybit 계정 2

---

### 시나리오 2: 거래소별로 계정 분리

**목적:** Binance 1개, Bybit 1개 계정만 사용

```bash
# .env 파일
# Binance 계정 (5분봉, 30분봉 공통)
BINANCE_API_KEY=binance_main_key
BINANCE_SECRET=binance_main_secret

# Bybit 계정 (15분봉, 1시간봉 공통)
BYBIT_API_KEY=bybit_main_key
BYBIT_API_SECRET=bybit_main_secret

TRADING_MODE=real
```

**결과:**

- 5분봉, 30분봉 → Binance 메인 계정
- 15분봉, 1시간봉 → Bybit 메인 계정

---

### 시나리오 3: 일부만 다른 계정 사용

**목적:** 특정 봇만 별도 계정 사용

```bash
# .env 파일
# Global Keys (대부분의 봇)
BINANCE_API_KEY=binance_main_key
BINANCE_SECRET=binance_main_secret
BYBIT_API_KEY=bybit_main_key
BYBIT_API_SECRET=bybit_main_secret

# 5분봉만 다른 계정 사용
BINANCE_API_KEY_5M=binance_special_key
BINANCE_SECRET_5M=binance_special_secret

TRADING_MODE=real
```

**결과:**

- 5분봉 → Binance 특별 계정
- 30분봉 → Binance 메인 계정
- 15분봉, 1시간봉 → Bybit 메인 계정

---

## ✅ 검증 방법

### 1. 환경 변수 확인

```bash
# .env 파일이 올바르게 설정되었는지 확인
cat .env | grep -E "API_KEY|SECRET"
```

### 2. 봇 로그 확인

각 봇이 시작될 때 어떤 API 키를 사용하는지 로그에 표시됩니다:

```bash
# 5분봉 봇 로그
tail -f Real_5m/bot.log

# 15분봉 봇 로그
tail -f Deploy_15m/bot.log

# 30분봉 봇 로그
tail -f BTC_30m/bot.log

# 1시간봉 봇 로그
tail -f Bybit_1h/bot.log
```

### 3. 대시보드에서 확인

대시보드(`http://localhost:8000`)에서 각 봇의 잔고를 확인하여 올바른 계정에 연결되었는지 확인할 수 있습니다.

---

## 🔐 보안 권장사항

### 1. API 키 권한 설정

각 거래소에서 API 키를 생성할 때:

✅ **허용:**

- 선물 거래 (Futures Trading)
- 잔고 조회 (Read Balance)
- 주문 생성/취소 (Create/Cancel Orders)

❌ **금지:**

- 출금 (Withdrawal)
- 전송 (Transfer)
- 서브 계정 관리

### 2. IP 화이트리스트

가능하면 서버 IP를 화이트리스트에 추가:

```
Binance: Account → API Management → Edit → IP Access Restriction
Bybit: Account & Security → API → Edit → IP Restriction
```

### 3. .env 파일 보안

```bash
# 권한 설정
chmod 600 .env

# Git에 커밋하지 않기
echo ".env" >> .gitignore

# 백업 시 주의
# .env 파일을 백업할 때는 암호화된 저장소 사용
```

---

## 🚨 문제 해결

### 문제 1: "Invalid API Key" 오류

**원인:** API 키가 잘못 입력되었거나 만료됨

**해결:**

1. .env 파일에서 API 키 확인
2. 거래소에서 API 키 상태 확인
3. 공백이나 특수문자가 없는지 확인

```bash
# API 키에 공백이 있는지 확인
cat .env | grep "API_KEY" | od -c
```

### 문제 2: "Permission Denied" 오류

**원인:** API 키에 필요한 권한이 없음

**해결:**

1. 거래소에서 API 키 권한 확인
2. 선물 거래 권한이 활성화되어 있는지 확인

### 문제 3: 봇이 다른 계정에 연결됨

**원인:** 환경 변수 우선순위 문제

**해결:**

```bash
# 봇별 전용 키가 설정되어 있는지 확인
grep "BINANCE_API_KEY_5M" .env
grep "BYBIT_API_KEY_15M" .env
grep "BINANCE_API_KEY_30M" .env
grep "BYBIT_API_KEY_1H" .env

# 비어있으면 Global 키를 사용함
```

---

## 📝 체크리스트

배포 전 확인사항:

- [ ] `.env` 파일 생성 완료
- [ ] 각 봇의 API 키 입력 완료
- [ ] API 키 권한 확인 (출금 권한 제거)
- [ ] IP 화이트리스트 설정 (선택)
- [ ] `.env` 파일 권한 설정 (`chmod 600`)
- [ ] Paper Trading으로 테스트 완료
- [ ] 각 봇의 잔고 확인
- [ ] 대시보드 접속 확인

---

## 🎯 다음 단계

1. ✅ API 키 설정 완료
2. ⏭️ Docker로 실행: `docker-compose up -d`
3. ⏭️ 대시보드 접속: `http://localhost:8000`
4. ⏭️ 각 봇 상태 확인
5. ⏭️ Paper Trading 테스트
6. ⏭️ Real Trading 전환 (신중하게!)

---

**주의:** Real Trading으로 전환하기 전에 반드시 Paper Trading으로 충분히 테스트하세요!
