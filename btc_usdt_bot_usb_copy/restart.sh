#!/bin/bash
pkill -f bot_manager.py
sleep 2
cd "/home/ser1/새 폴더/btc/usdt 봇 통합관리"
nohup python3 bot_manager.py > dashboard.log 2>&1 &
echo "✅ 봇 재시작됨!"
echo "📊 대시보드: http://localhost:8000"
