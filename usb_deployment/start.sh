#!/bin/bash

# 실행 권한 부여
chmod +x "$0"
chmod +x setup.sh

echo "🚀 통합 봇 대시보드 및 서비스 시작 (Universal Launcher)..."

# 1. 도커 명령어 자동 감지 (새 서버 호환성 확보)
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
else
    echo "❌ Docker Compose가 설치되지 않았습니다. 먼저 ./setup.sh를 실행해주세요."
    exit 1
fi

echo "ℹ️  사용 중인 도커 명령어: $DOCKER_COMPOSE_CMD"

# 2. 기존 서비스 중단 (안전한 재시작)
echo "♻️  기존 서비스 정리 중..."
sudo $DOCKER_COMPOSE_CMD down

# 3. 서비스 빌드 및 실행
echo "🏗️  서비스 빌드 및 시작..."
sudo $DOCKER_COMPOSE_CMD up -d --build

echo ""
echo "✅ 실행 완료!"
echo "---------------------------------------------------"
echo "🌐 웹 대시보드 접속: http://localhost:8080"
echo "   (내부망 접속 시: http://[서버IP]:8080)"
echo "---------------------------------------------------"
echo "📝 로그 확인: sudo $DOCKER_COMPOSE_CMD logs -f"
