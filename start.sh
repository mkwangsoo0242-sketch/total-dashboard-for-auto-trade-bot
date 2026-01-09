#!/bin/bash
cd "/home/ser1/새 폴더/btc/usdt 봇 통합관리"
# 모든 봇 폴더를 PYTHONPATH에 추가하여 임포트 에러 원천 차단
export PYTHONPATH=$PYTHONPATH:$(pwd):$(pwd)/"BTC_30분봉_Live":$(pwd)/"RealTradingBot_Deployment(5분봉)":$(pwd)/"bybit_bot_usb(1시간-통합)":$(pwd)/"deploy_package--15분봉"
nohup python3 -u bot_manager.py > manager.log 2>&1 &
echo "✅ 봇 시작됨!"
echo "📊 대시보드: http://localhost:8000"
