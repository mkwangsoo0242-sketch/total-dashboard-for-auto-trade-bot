#!/bin/bash

# High ROI Bot Execution Script
# This script sets up a virtual environment and starts the web dashboard.

echo "=========================================="
echo "   Starting High ROI Trading Bot System   "
echo "=========================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed. Please install it first."
    exit 1
fi

# Create and activate virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "[1/3] Creating virtual environment (.venv)..."
    python3 -m venv .venv
fi

echo "[2/3] Activating virtual environment and installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[3/3] Starting Web Dashboard & Bot Controller..."
echo "Dashbaord will be available at: http://localhost:5000"
echo "Press Ctrl+C to stop."

# Run Flask app
# The app.py will handle starting/stopping the main bot (main.py)
python3 frontend/app.py
