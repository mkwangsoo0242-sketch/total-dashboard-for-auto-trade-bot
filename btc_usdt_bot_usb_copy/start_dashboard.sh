#!/bin/bash

# 스크립트가 위치한 디렉토리로 이동
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "기존 봇 대시보드 컨테이너를 중지합니다..."
docker-compose down

echo "도커 컴포즈를 사용하여 봇 대시보드를 빌드하고 시작합니다..."
docker-compose up --build -d

echo "봇 대시보드가 도커에서 시작되었습니다. http://localhost:8000 에서 접속하세요."
echo "로그를 보려면: docker-compose logs -f"
echo "중지하려면: docker-compose down"