# Bybit 1시간봉 통합 실거래 봇

이 프로젝트는 Bybit 거래소를 위한 적응형 전략 기반 실거래 봇입니다. 1시간봉 데이터를 기반으로 시장 상황(추세/횡보)을 판단하고 최적의 진입 및 청산 전략을 실행합니다.

## 주요 기능

- **적응형 전략 (Adaptive Strategy)**: 시장 상황(Trending/Ranging)에 따라 파라미터를 동적으로 조정합니다.
- **ML 필터링**: XGBoost 모델(`trend_xgb.pkl`)을 활용하여 진입 신호의 신뢰도를 높입니다.
- **자동 최적화**: `auto_optimizer.py`를 통해 매일 시장 데이터를 학습하고 최적의 파라미터를 갱신합니다.
- **실시간 모니터링**: Flask 기반의 웹 대시보드(`web_dashboard.py`)를 통해 거래 상태와 로그를 실시간으로 확인할 수 있습니다.
- **KST 시간대 지원**: 모든 로그와 데이터는 한국 표준시(KST)를 기준으로 기록됩니다.

## 파일 구조

| 파일명 | 설명 |
| :--- | :--- |
| `live_trader_bybit.py` | 실거래 봇 메인 실행 파일 |
| `strategy.py` | 지표 계산 및 트레이딩 전략 로직 |
| `bybit_client.py` | Bybit API 연동 클라이언트 |
| `auto_optimizer.py` | 파라미터 자동 최적화 스크립트 |
| `web_dashboard.py` | 웹 기반 모니터링 대시보드 |
| `config.py` | API 키 및 트레이딩 설정 |
| `dynamic_config.json` | 최적화된 동적 파라미터 저장 파일 |
| `trading_status.json` | 대시보드용 실시간 상태 데이터 |
| `bot.log` | 트레이딩 활동 로그 |

## 실행 방법

### 1. 환경 설정
`.env` 파일에 Bybit API Key와 Secret을 설정합니다.
```env
BYBIT_API_KEY=your_api_key
BYBIT_API_SECRET=your_api_secret
```

### 2. 봇 실행 (선택 사항)

#### 방법 A: PM2 사용 (추천 - 간편한 모니터링)
```bash
# 설치 (최초 1회)
# npm install pm2 -g

# 실행
pm2 start ecosystem.config.js

# 상태 확인
pm2 monit
```

#### 방법 B: Docker 사용 (격리된 환경)
```bash
# 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

#### 방법 C: 일반 실행 (Nohup)
```bash
nohup python3 -u live_trader_bybit.py > bot_stdout.log 2>&1 &
```

## 최근 업데이트
- `KSTFormatter`를 통한 로그 시간대 오류 및 포맷팅 이슈 해결
- `FlushFileHandler` 적용으로 `bot.log` 실시간 업데이트 보장
- 메인 루프 실행 주기를 10초로 최적화하여 반응성 향상
