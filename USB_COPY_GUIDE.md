# 📦 USB 복사 및 다른 서버 배포 가이드

## ✅ 준비 완료

모든 봇이 Bybit을 사용하도록 설정되었고, USB에 복사할 준비가 완료되었습니다.

---

## 📁 압축 파일 정보

- **파일명:** `usb_deployment_bybit_final.tar.gz`
- **크기:** 34MB
- **위치:** `/home/ser1/새 폴더/btc/usdt 봇 통합관리/`
- **포함 내용:**
  - 4개 트레이딩 봇 (모두 Bybit 사용)
  - 통합 대시보드
  - Docker 설정
  - 배포 가이드 문서

---

## 🔧 USB 복사 방법

### 방법 1: GUI로 복사 (가장 쉬움)

1. **USB 연결**
   - USB를 컴퓨터에 연결
   - 자동으로 마운트됨 (보통 `/media/ser1/USB이름/`)

2. **파일 탐색기로 복사**

   ```bash
   # 파일 탐색기 열기
   nautilus "/home/ser1/새 폴더/btc/usdt 봇 통합관리/" &
   ```

3. **드래그 앤 드롭**
   - `usb_deployment_bybit_final.tar.gz` 파일을 USB로 드래그

---

### 방법 2: 터미널로 복사 (권장)

```bash
# 1. USB 마운트 위치 확인
lsblk
# 또는
df -h | grep media

# 2. USB로 복사 (USB 경로를 실제 경로로 변경)
cp "/home/ser1/새 폴더/btc/usdt 봇 통합관리/usb_deployment_bybit_final.tar.gz" /media/ser1/USB이름/

# 3. 복사 확인
ls -lh /media/ser1/USB이름/usb_deployment_bybit_final.tar.gz

# 4. 안전하게 USB 제거
sync
umount /media/ser1/USB이름
```

---

## 🚀 다른 서버에서 배포하기

### 1단계: USB에서 파일 복사

```bash
# 새 서버에서 USB 마운트 확인
lsblk

# 홈 디렉토리로 복사
cp /media/user/USB이름/usb_deployment_bybit_final.tar.gz ~/

# 압축 해제
cd ~
tar -xzf usb_deployment_bybit_final.tar.gz
cd usb_deployment
```

### 2단계: 환경 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집 (각 봇의 Bybit API 키 입력)
nano .env
```

**.env 파일 예시:**

```bash
# 각 봇마다 다른 Bybit 계정 사용
BYBIT_API_KEY_5M=your_account1_api_key
BYBIT_API_SECRET_5M=your_account1_secret

BYBIT_API_KEY_15M=your_account2_api_key
BYBIT_API_SECRET_15M=your_account2_secret

BYBIT_API_KEY_30M=your_account3_api_key
BYBIT_API_SECRET_30M=your_account3_secret

BYBIT_API_KEY_1H=your_account4_api_key
BYBIT_API_SECRET_1H=your_account4_secret

TRADING_MODE=paper  # 처음엔 paper로 테스트!
```

### 3단계: Docker로 실행 (권장)

```bash
# Docker 설치 (없는 경우)
chmod +x setup.sh
./setup.sh

# 실행
chmod +x start.sh
./start.sh

# 로그 확인
docker-compose logs -f
```

### 4단계: 대시보드 접속

```
http://서버IP:8000
```

---

## 📋 체크리스트

배포 전 확인사항:

### USB 복사 전

- [x] 최종 압축 파일 생성 완료
- [x] 모든 봇 Bybit 전환 완료
- [x] Docker 설정 검증 완료
- [x] 환경 변수 로딩 로직 검증 완료

### USB 복사 후

- [ ] USB에 파일 복사 완료
- [ ] 파일 크기 확인 (34MB)
- [ ] 안전하게 USB 제거

### 새 서버 배포 시

- [ ] 압축 파일 해제
- [ ] .env 파일 생성 및 API 키 입력
- [ ] API 키 권한 확인 (출금 권한 제거)
- [ ] Docker 설치
- [ ] 봇 실행
- [ ] 대시보드 접속 확인
- [ ] Paper Trading 테스트

---

## 🔐 보안 권장사항

### 1. API 키 권한 설정

Bybit에서 API 키 생성 시:

✅ **허용:**

- 선물 거래 (Derivatives Trading)
- 잔고 조회 (Read)
- 주문 생성/취소 (Trade)

❌ **금지:**

- 출금 (Withdraw)
- 전송 (Transfer)
- 서브 계정 관리

### 2. IP 화이트리스트

```
Bybit → Account & Security → API → Edit → IP Restriction
```

새 서버의 IP 주소를 추가하세요.

### 3. .env 파일 보안

```bash
# 권한 설정
chmod 600 .env

# Git에 커밋하지 않기
echo ".env" >> .gitignore
```

---

## 🎯 포함된 문서

배포 패키지에 포함된 가이드:

1. **DEPLOYMENT_GUIDE.md** - 전체 배포 가이드
2. **API_KEY_GUIDE.md** - API 키 설정 상세 가이드
3. **README_UPDATED.md** - 업데이트 요약
4. **docker-compose.yml** - Docker 설정
5. **setup.sh** - 자동 설치 스크립트
6. **start.sh** - 시작 스크립트

---

## 🚨 문제 해결

### USB 인식 안 됨

```bash
# USB 장치 확인
lsblk
dmesg | tail

# 수동 마운트
sudo mkdir -p /mnt/usb
sudo mount /dev/sdb1 /mnt/usb  # sdb1은 실제 장치명으로 변경
```

### 복사 중 오류

```bash
# 디스크 공간 확인
df -h

# USB 파일시스템 확인
sudo fsck /dev/sdb1
```

### 새 서버에서 실행 안 됨

```bash
# Docker 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs dashboard_api
docker-compose logs btc_30m_bot

# 재시작
docker-compose restart
```

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

## ✅ 최종 확인

모든 준비가 완료되었습니다!

1. ✅ 압축 파일 생성: `usb_deployment_bybit_final.tar.gz` (34MB)
2. ✅ 모든 봇 Bybit 전환 완료
3. ✅ 각 봇마다 다른 API 키 사용 가능
4. ✅ Docker 설정 검증 완료
5. ✅ 배포 가이드 문서 포함

**USB에 복사하고 다른 서버에 배포하세요!** 🚀

---

## 🎉 다음 단계

1. USB에 파일 복사
2. 새 서버로 이동
3. 압축 해제
4. .env 파일 설정
5. Docker로 실행
6. 대시보드 접속
7. Paper Trading 테스트
8. Real Trading 전환 (신중하게!)

**주의:** Real Trading으로 전환하기 전에 반드시 Paper Trading으로 충분히 테스트하세요!
