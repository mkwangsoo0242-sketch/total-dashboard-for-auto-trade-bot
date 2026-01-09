#!/bin/bash
cd "/home/ser1/새 폴더/btc/usdt 봇 통합관리"
nohup ./venv/bin/python -u bot_manager.py > manager.log 2>&1 &
echo "✅ 봇 시작됨!"
echo "📊 대시보드: http://localhost:8000"
