# RealTradingBot 배포 가이드

이 가이드는 새로운 서버에 RealTradingBot을 배포하고 실행하는 방법에 대한 지침을 제공합니다.

## 1. 프로젝트 구조

`RealTradingBot_Deployment` 폴더에는 다음 핵심 파일이 포함되어 있습니다:
- `live_trading_bot.py`: 실시간 또는 모의 거래를 위한 메인 스크립트.
- `backtester.py`: 거래 전략을 백테스트하기 위한 스크립트.
- `data_collector.py`: 과거 시장 데이터를 수집하고 업데이트하기 위한 스크립트.
- `strategy.py`: 거래 전략에 사용되는 기술 지표를 정의합니다.
- `train_trend_model.py`: XGBoost 추세 예측 모델을 훈련하기 위한 스크립트.
- `requirements.txt`: 모든 Python 종속성을 나열합니다.
- `.env.example`: 구성 예시 환경 파일.

## 2. 환경 설정

1.  **Python 설치**: 서버에 Python 3.8 이상이 설치되어 있는지 확인하십시오.
    ```bash
    sudo apt update
    sudo apt install python3 python3-pip python3-venv
    ```

2.  **가상 환경 생성 및 활성화**:
    종속성 관리를 위해 가상 환경을 사용하는 것이 좋습니다.
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **종속성 설치**:
    `RealTradingBot_Deployment` 디렉토리로 이동하여 필요한 Python 패키지를 설치하십시오:
    ```bash
    cd /path/to/RealTradingBot_Deployment
    pip install -r requirements.txt
    ```

## 3. 구성

1.  **환경 변수**:
    `.env.example` 파일을 `.env`로 복사하고 Binance API 키와 시크릿을 입력하십시오.
    ```bash
    cp .env.example .env
    ```
    `.env` 파일 편집:
    ```
    BINANCE_API_KEY=your_api_key_here
    BINANCE_SECRET=your_secret_key_here
    TRADING_MODE=paper # 또는 실시간 거래를 위한 'real'
    SYMBOL=BTC/USDT
    LEVERAGE=10
    RISK_PER_TRADE=0.02
    ```
    - `TRADING_MODE`: 모의 거래를 위해 `paper`로 설정하거나 실시간 거래를 위해 `real`로 설정하십시오.
    - `SYMBOL`: 거래 쌍 (예: `BTC/USDT`).
    - `LEVERAGE`: 원하는 레버리지.
    - `RISK_PER_TRADE`: 거래당 위험을 감수할 잔고의 백분율 (예: 2%의 경우 0.02).

## 4. 데이터 준비

봇은 모델 훈련을 위해 BTC/USDT에 대한 3년치 5분 OHLCV 과거 데이터가 필요합니다. 이 파일(`data/btc_usdt_5m_3y.csv`)은 크기가 커서 배포 패키지에 의도적으로 포함되지 않았습니다.

1.  **`data` 디렉토리 생성**:
    ```bash
    mkdir data
    ```

2.  **초기 데이터 수집**:
    `data_collector.py` 스크립트를 실행하여 초기 3년치 5분 BTC/USDT 데이터를 가져오십시오. 이렇게 하면 `data/btc_usdt_5m_3y.csv`가 생성됩니다.
    ```bash
    python3 data_collector.py
    ```
    *참고: 이 과정은 대량의 과거 데이터를 가져오고 바이낸스 API 속도 제한으로 인해 상당한 시간이 소요될 수 있습니다.* 

## 5. 모델 훈련

데이터를 준비한 후 XGBoost 추세 예측 모델을 훈련해야 합니다.

1.  **모델 훈련**:
    `train_trend_model.py` 스크립트를 실행하십시오. 이렇게 하면 루트 디렉토리에 `trend_xgb.pkl`이 생성됩니다.
    ```bash
    python3 train_trend_model.py
    ```
    *참고: 이 과정에는 데이터 리샘플링, 특징 엔지니어링 및 하이퍼파라미터 튜닝이 포함되며, 이는 CPU 집약적일 수 있습니다.* 

## 6. 봇 실행

### 6.1. 백테스팅

과거 데이터로 전략을 검증하려면 `backtester.py` 스크립트를 실행하십시오:

```bash
python3 backtester.py
```
백테스터는 `data/btc_usdt_5m_3y.csv` 및 `trend_xgb.pkl` 모델을 로드한 다음 거래를 시뮬레이션하고 성능 지표를 출력합니다.

### 6.2. 실시간/모의 거래

실시간 또는 모의 거래 봇을 시작하려면:

```bash
python3 live_trading_bot.py
```
봇은 실시간 데이터를 지속적으로 가져오고, 신호를 생성하며, `.env` 구성에 따라 거래를 실행합니다.

## 7. 자동 데이터 업데이트 및 모델 재훈련

데이터와 모델을 최신 상태로 유지하려면 `update_and_retrain.py` 스크립트를 사용할 수 있습니다. 이 스크립트는 다음을 수행합니다:
1.  과거 데이터(`data/btc_usdt_5m_3y.csv`)를 최신 캔들로 업데이트합니다.
2.  업데이트된 데이터를 사용하여 `trend_xgb.pkl` 모델을 재훈련합니다.

이 스크립트를 `cron` (Linux) 또는 `APScheduler` (Python 라이브러리)를 사용하여 주기적으로 (예: 매일 또는 매주) 실행하도록 예약할 수 있습니다.

**`cron` 작업 예시 (매일 오전 3시에 실행):**
1.  크론탭을 엽니다:
    ```bash
    crontab -e
    ```
2.  다음 줄을 추가하십시오 (`/path/to/RealTradingBot_Deployment`를 실제 경로로 바꾸십시오):
    ```
    0 3 * * * /usr/bin/python3 /path/to/RealTradingBot_Deployment/update_and_retrain.py >> /path/to/RealTradingBot_Deployment/update_log.log 2>&1
    ```
    *참고: Python 실행 파일 경로가 환경에 맞는지 확인하십시오 (예: `/usr/bin/python3` 또는 `/usr/bin/env python3`). 가상 환경을 사용하는 경우 먼저 활성화하거나 가상 환경의 Python 실행 파일의 전체 경로를 사용해야 할 수 있습니다.*

이것으로 배포 가이드가 완료됩니다.
