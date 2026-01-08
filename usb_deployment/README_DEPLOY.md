# 🚀 통합 봇 대시보드 배포 가이드

봇 관리 시스템이 **설정(Setup)**과 **실행(Start)** 단계로 깔끔하게 분리되었습니다.

## 1. 초기 설정 (최초 1회)

처음 설치하거나 API 설정을 바꿀 때만 실행하세요.
Docker를 설치하고 각 봇의 비밀번호(API Key)를 설정해줍니다.

```bash
chmod +x setup.sh
./setup.sh
```

## 2. 봇 및 대시보드 실행 (일상 사용)

봇을 켜거나, 업데이트 후 재시작할 때 사용합니다.
모든 봇과 웹 대시보드가 한 번에 켜집니다.

```bash
chmod +x start.sh
sudo ./start.sh
```

## 3. 접속 정보

- **웹 대시보드**: `http://localhost:8080`
- **핸드폰 접속**: `http://[컴퓨터IP]:8080` (같은 와이파이 필수)

## 4. 기타 명령어

- **로그 전체 확인**: `docker-compose logs -f`
- **전체 중지**: `docker-compose down`
