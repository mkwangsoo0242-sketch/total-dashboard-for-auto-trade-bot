#!/bin/bash

# Kill existing processes
echo "Killing existing bot manager and uvicorn processes..."
pkill -f "bot_manager.py"
pkill -f "uvicorn"

# Wait a moment
sleep 2

# Set Trading Mode to Paper for safety
export TRADING_MODE=paper

# Start the bot manager
echo "Starting Bot Dashboard..."
cd "/home/ser1/새 폴더/btc/usdt 봇 통합관리"

nohup python3 bot_manager.py > dashboard.log 2>&1 &

echo "Dashboard started. PID: $!"
echo "Check dashboard.log for output."