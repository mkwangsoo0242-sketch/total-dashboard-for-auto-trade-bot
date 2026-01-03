# Python 3.12 슬림 이미지 사용
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /app

# 필수 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 로그 및 데이터 저장을 위한 볼륨 설정
VOLUME ["/app/logs", "/app/data"]

# 대시보드 포트 노출
EXPOSE 5000

# 봇 실행 (기본값)
CMD ["python", "-u", "live_trader_bybit.py"]
