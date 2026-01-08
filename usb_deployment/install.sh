#!/bin/bash

echo "========================================================"
echo "🤖 트레이딩 봇 통합 설치 및 실행 스크립트 (Docker)"
echo "========================================================"

# 1. Docker 설치 확인
if ! command -v docker &> /dev/null; then
    echo "📦 Docker를 설치합니다..."
    
    # 패키지 목록 업데이트
    sudo apt-get update
    
    # 필수 패키지 설치
    sudo apt-get install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release
    
    # Docker GPG 키 추가
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    # 리포지토리 설정
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
      
    # Docker 설치
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-compose

    # 권한 설정 (현재 사용자를 docker 그룹에 추가)
    sudo usermod -aG docker $USER
    echo "✅ Docker 설치 완료. (권한 적용을 위해 재부팅이 필요할 수 있습니다)"
else
    echo "✅ Docker가 이미 설치되어 있습니다."
fi

# 2. Docker Compose 실행
echo "🚀 봇 컨테이너를 빌드하고 실행합니다..."

# Docker Compose가 플러그인 버전인지 독립형인지 확인하여 실행
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

# 백그라운드에서 빌드 및 실행
sudo $DOCKER_COMPOSE_CMD up -d --build

# 3. 자동 실행 설정 (Systemd)
# Docker는 기본적으로 서비스가 활성화되어 있으면 재부팅 시 컨테이너도(restart: always 정책으로 인해) 자동 실행됩니다.
# 하지만 확실하게 하기 위해 Docker 서비스를 활성화합니다.
echo "🔄 부팅 시 Docker 자동 실행 설정..."
sudo systemctl enable docker.service
sudo systemctl enable containerd.service

echo "========================================================"
echo "✨ 설치가 완료되었습니다!"
echo ""
echo "봇들은 이제 백그라운드에서 실행되며, 컴퓨터가 켜질 때마다 자동으로 시작됩니다."
echo ""
echo "📊 상태 확인 명령어: sudo $DOCKER_COMPOSE_CMD ps"
echo "📜 로그 확인 명령어: sudo $DOCKER_COMPOSE_CMD logs -f"
echo "🛑 중지 명령어:     sudo $DOCKER_COMPOSE_CMD down"
echo "========================================================"
