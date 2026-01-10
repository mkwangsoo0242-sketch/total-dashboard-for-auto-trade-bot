#!/bin/bash

# Kill existing processes
echo "Killing existing bot manager and uvicorn processes..."
pkill -f "bot_manager.py"
pkill -f "uvicorn"

# Wait a moment
sleep 2

# [CRON FIX] Define PATH explicitly to ensure commands like python3, pkill are found
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Logging start time
echo "--- Starting Dashboard at $(date) ---" >> dashboard_boot.log

# Add PYTHONPATH for robust imports
export PYTHONPATH=$PYTHONPATH:$(pwd):$(pwd)/"BTC_30분봉_Live":$(pwd)/"RealTradingBot_Deployment(5분봉)":$(pwd)/"bybit_bot_usb(1시간-통합)":$(pwd)/"deploy_package--15분봉"

# Set Trading Mode to Paper for safety
export TRADING_MODE=paper

# Start the bot manager
echo "Starting Bot Dashboard..."
cd "/home/ser1/새 폴더/btc/usdt 봇 통합관리"

nohup python3 -u bot_manager.py > dashboard.log 2>&1 &
PID=$!

sleep 2

if ps -p $PID > /dev/null; then
  echo "Dashboard started successfully. PID: $PID"
  echo "Check dashboard.log for output."
else
  echo "Dashboard failed to start. Checking log:"
  cat dashboard.log
fi