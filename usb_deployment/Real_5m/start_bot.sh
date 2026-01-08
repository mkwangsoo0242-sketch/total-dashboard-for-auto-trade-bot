#!/bin/bash

# 스크립트가 있는 디렉토리로 이동
cd "$(dirname "$0")"

# 가상환경이 있다면 활성화 (선택 사항)
# source venv/bin/activate

echo "🚀 RealTradingBot을 시작합니다..."
echo "로그 파일: bot.log"

# 봇 실행 (백그라운드 실행을 원하면 nohup 사용)
# python3 live_trading_bot.py

# 사용자가 보기 편하게 포그라운드 실행 (로그는 파일과 화면 동시 출력)
python3 live_trading_bot.py 2>&1 | tee -a bot.log
