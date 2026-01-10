#!/bin/bash

# Check running as root
if [ "$EUID" -ne 0 ]; then
  echo "❌ 관리자 권한으로 실행해주세요 (sudo ./setup_log_rotate.sh)"
  exit 1
fi

LOG_CONFIG="/etc/logrotate.d/trading_bot"
# 현재 경로 자동 감지
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "🔄 매일 로그 자동 삭제 설정 중... (경로: $SCRIPT_DIR)"

cat > $LOG_CONFIG <<EOF
$SCRIPT_DIR/*.log $SCRIPT_DIR/*/*.log {
    daily
    missingok
    rotate 1
    compress
    delaycompress
    notifempty
    create 640 $SUDO_USER $SUDO_USER
    copytruncate
}
EOF

echo "✅ 설정 완료!" 
echo "   - 매일 밤 자동으로 로그를 정리합니다."
echo "   - 최근 1일치만 남기고 나머지는 자동 삭제됩니다."
