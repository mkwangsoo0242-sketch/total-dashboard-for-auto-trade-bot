# USB 봇 사용 가이드

이 가이드는 USB에 복사된 봇 시스템을 다른 컴퓨터에서 실행하고 관리하는 방법을 설명합니다.

---

### 1. 파일 구조

USB에 복사된 폴더 (`btc_usdt_bot_usb_copy`)는 다음과 같은 주요 파일 및 디렉토리를 포함합니다:

```
btc_usdt_bot_usb_copy/
├── .env                  # 환경 변수 설정 파일 (API 키 등)
├── bot_manager.py        # 봇 관리 및 대시보드 실행 스크립트
├── start_dashboard.sh    # 대시보드 시작 스크립트 (Linux/macOS)
├── dashboard.log         # 대시보드 로그 파일
├── templates/            # 웹 대시보드 템플릿 파일
├── bots/                 # 봇 관련 스크립트 및 설정 파일
│   ├── BTC_30분봉_Live/
│   │   ├── live_bot.py
│   │   └── strategy_30m.py
│   ├── RealTradingBot_Deployment(5분봉)/
│   │   ├── live_trading_bot.py
│   │   └── strategy_5m.py
│   └── bybit_bot_usb(1시간-통합)/
│       ├── final_bot_1h.py
│       └── strategy_1h.py
├── strategy_*.py         # 개별 전략 파일 (예: strategy_30m.py, strategy_5m.py, strategy_1h.py)
└── *.pkl                 # XGBoost 모델 파일 (예: model_30m.pkl, model_5m.pkl, model_1h.pkl)
```

---

### 2. 환경 설정 (.env 파일)

봇을 실행하기 전에 `.env` 파일을 올바르게 설정해야 합니다. 이 파일에는 거래소 API 키와 같은 민감한 정보가 포함됩니다.

1.  `btc_usdt_bot_usb_copy` 폴더 내의 `.env` 파일을 텍스트 편집기로 엽니다.
2.  다음 변수들을 본인의 거래소 API 키와 시크릿 키로 업데이트합니다:

    ```
    BYBIT_API_KEY=YOUR_BYBIT_API_KEY
    BYBIT_SECRET_KEY=YOUR_BYBIT_SECRET_KEY
    ```
    **주의**: 이 정보는 외부에 노출되지 않도록 주의하십시오.

---

### 3. 도커 설치 (필수)

봇 대시보드를 실행하려면 시스템에 Docker와 Docker Compose가 설치되어 있어야 합니다.

*   **Linux**: [Docker 공식 문서](https://docs.docker.com/engine/install/ubuntu/)를 참조하여 설치하십시오.
*   **Windows**: [Docker Desktop 공식 문서](https://docs.docker.com/desktop/install/windows-install/)를 참조하여 설치하십시오.
*   **macOS**: [Docker Desktop 공식 문서](https://docs.docker.com/desktop/install/mac-install/)를 참조하여 설치하십시오.

설치 후 터미널에서 다음 명령어를 실행하여 Docker가 올바르게 설치되었는지 확인하십시오:

```bash
docker --version
docker compose version
```

---

### 4. 대시보드 실행

대시보드는 봇의 상태를 모니터링하고 관리하는 웹 인터페이스를 제공합니다. **도커를 사용하여 실행하는 것을 권장합니다.**

1.  **터미널 열기**:
    `btc_usdt_bot_usb_copy` 폴더로 이동하여 터미널(또는 명령 프롬프트)을 엽니다.

2.  **대시보드 시작 스크립트 실행 (도커 사용)**:
    `start_dashboard.sh` 스크립트를 실행하여 도커 컴포즈를 통해 대시보드를 시작합니다.

    ```bash
    ./start_dashboard.sh
    ```
    이 스크립트는 도커 이미지를 빌드하고 컨테이너를 백그라운드에서 실행합니다.

    **참고**: 도커를 사용하지 않고 직접 Python 환경에서 실행하려면, 필요한 Python 라이브러리들을 수동으로 설치한 후 `python bot_manager.py` 명령어를 사용해야 합니다. (이 방법은 권장하지 않습니다.)

3.  **대시보드 접속**:
    스크립트가 성공적으로 실행되면, 웹 브라우저를 열고 다음 주소로 접속합니다:
    `http://127.0.0.1:8000` 또는 `http://localhost:8000`

4.  **로그 확인 및 중지**:
    *   컨테이너 로그를 실시간으로 확인하려면: `docker-compose logs -f`
    *   대시보드를 중지하려면: `docker-compose down`

---

### 5. 봇 관리 (대시보드에서)

대시보드에 접속하면 다음 기능을 사용할 수 있습니다:

*   **봇 시작/중지**: 각 봇 옆의 버튼을 사용하여 개별 봇을 시작하거나 중지할 수 있습니다.
*   **로그 확인**: 대시보드에서 실시간 봇 로그를 확인할 수 있습니다.
*   **상태 모니터링**: 봇의 현재 상태(실행 중, 중지됨 등)를 확인할 수 있습니다.

---

### 6. 문제 해결

*   **도커 설치 문제**: Docker 또는 Docker Compose가 올바르게 설치되었는지 확인하십시오.
*   **컨테이너 시작 실패**: `docker-compose logs` 명령어를 사용하여 컨테이너 로그를 확인하고 오류 메시지를 분석하십시오.
*   **API 키 오류**: `.env` 파일에 올바른 API 키와 시크릿 키가 설정되어 있는지 다시 확인하십시오.
*   **대시보드 접속 불가**: 방화벽 설정이 `8000` 포트를 차단하고 있지 않은지 확인하십시오.

---

### 7. 시스템 부팅 시 자동 실행 (Linux Systemd)

Linux 시스템에서 컴퓨터 부팅 시 봇 대시보드가 자동으로 시작되도록 설정할 수 있습니다.

1.  **서비스 파일 복사**:
    `bot_manager.service` 파일을 시스템의 `systemd` 서비스 디렉토리로 복사합니다.

    ```bash
    sudo cp /home/ser1/새 폴더/btc/usdt 봇 통합관리/btc_usdt_bot_usb_copy/bot_manager.service /etc/systemd/system/
    ```
    **주의**: 위 경로에서 `/home/ser1/새 폴더/btc/usdt 봇 통합관리/btc_usdt_bot_usb_copy/` 부분은 실제 USB 복사본이 마운트된 경로로 변경해야 합니다.

2.  **systemd 데몬 재로드**:
    새로운 서비스 파일을 인식하도록 `systemd` 데몬을 재로드합니다.

    ```bash
    sudo systemctl daemon-reload
    ```

3.  **서비스 활성화 및 시작**:
    부팅 시 자동으로 시작되도록 서비스를 활성화하고, 즉시 서비스를 시작합니다.

    ```bash
    sudo systemctl enable bot_manager.service
    sudo systemctl start bot_manager.service
    ```

4.  **서비스 상태 확인**:
    서비스가 올바르게 실행 중인지 확인합니다.

    ```bash
    sudo systemctl status bot_manager.service
    ```

5.  **서비스 중지 및 비활성화 (선택 사항)**:
    자동 실행을 중지하고 싶다면 다음 명령어를 사용합니다.

    ```bash
    sudo systemctl stop bot_manager.service
    sudo systemctl disable bot_manager.service
    ```

---

이 가이드가 USB 복사본을 사용하여 봇을 성공적으로 운영하는 데 도움이 되기를 바랍니다.
