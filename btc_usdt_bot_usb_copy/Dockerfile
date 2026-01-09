# Python 3.9 기반 이미지 사용
FROM python:3.9-slim-buster

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 환경 변수 설정 (컨테이너 내부에서 .env 파일을 사용하도록)
# .env 파일은 docker-compose.yml에서 볼륨 마운트될 예정이므로, 여기서는 복사하지 않음

# 포트 노출 (FastAPI 기본 포트)
EXPOSE 8000

# 컨테이너 시작 시 실행될 명령어
# bot_manager.py가 uvicorn을 사용하여 FastAPI 앱을 실행한다고 가정
CMD ["python", "bot_manager.py"]
