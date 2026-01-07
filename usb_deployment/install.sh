#!/bin/bash

# 에러 발생 시 중단
set -e

echo "========================================================"
echo "🤖 봇 자동 설치 및 실행 스크립트"
echo "========================================================"

# 1. Docker 설치 확인 및 설치
if ! command -v docker &> /dev/null; then
    echo "📦 Docker가 설치되어 있지 않습니다. 설치를 시작합니다..."
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose
    
    # 현재 사용자를 docker 그룹에 추가 (재로그인 필요할 수 있음)
    sudo usermod -aG docker $USER
    echo "✅ Docker 설치 완료"
else
    echo "✅ Docker가 이미 설치되어 있습니다."
fi

# 2. Docker Compose 설치 확인 (docker-compose 또는 docker compose)
if ! command -v docker-compose &> /dev/null; then
     if ! docker compose version &> /dev/null; then
        echo "📦 Docker Compose를 설치합니다..."
        sudo apt-get install -y docker-compose
     fi
fi

# 3. 서비스 실행
echo "🚀 봇 컨테이너를 빌드하고 실행합니다..."
# 권한 문제 방지를 위해 sudo 사용
sudo docker-compose up -d --build

echo "========================================================"
echo "✨ 설치 및 실행이 완료되었습니다!"
echo "📡 상태 확인: sudo docker-compose ps"
echo "📜 로그 확인: sudo docker-compose logs -f"
echo "========================================================"
