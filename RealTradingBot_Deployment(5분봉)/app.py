from flask import Flask, jsonify, render_template, request
import os
import json
import time
import subprocess
import signal
import ccxt
from dotenv import load_dotenv

app = Flask(__name__)

# Base directory where live_trading_bot.py is located (one level up)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(BASE_DIR, 'bot.log')
STATE_FILE = os.path.join(BASE_DIR, 'paper_trade_state.json')
PID_FILE = os.path.join(BASE_DIR, 'bot.pid')
MAIN_SCRIPT = os.path.join(BASE_DIR, 'live_trading_bot.py')

cached_balance = {
    "balance": 0.0,
    "currency": "USDT",
    "timestamp": 0
}

def get_real_balance():
    global cached_balance
    if time.time() - cached_balance['timestamp'] < 10:
        return cached_balance
    
    try:
        # Load .env
        env_path = os.path.join(BASE_DIR, '.env')
        load_dotenv(env_path)

        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_SECRET')
        
        if api_key and api_secret:
            # Use Binance as per user's setup
            exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'options': {'defaultType': 'future'},
            })
            # Fetch balance
            balance_data = exchange.fetch_balance()
            usdt = balance_data['total'].get('USDT', 0.0)
            
            cached_balance = {
                "balance": float(usdt),
                "currency": "USDT",
                "timestamp": time.time()
            }
        else:
            cached_balance["currency"] = "USDT" # Default
            
    except Exception as e:
        print(f"Error fetching balance: {e}")
    
    return cached_balance

def is_bot_running():
    # 1. Check PID file
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            # Check if process exists
            os.kill(pid, 0)
            return True, pid
        except (OSError, ValueError):
            # PID file exists but process doesn't, or invalid content
            pass
            
    # 2. Check for any running live_trading_bot.py process using pgrep
    try:
        result = subprocess.check_output(['pgrep', '-f', 'python3.*live_trading_bot.py'])
        pids = [int(p) for p in result.split()]
        if pids:
            return True, pids[0]
    except subprocess.CalledProcessError:
        pass

    return False, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    # 1. Bot Running Status
    running, pid = is_bot_running()
    
    # 2. Paper Trading Data
    trade_data = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                trade_data = json.load(f)
        except:
            trade_data = {"error": "Failed to load state"}
    
    # 3. Real Balance
    real_balance = get_real_balance()

    return jsonify({
        "running": running,
        "pid": pid,
        "trade_data": trade_data,
        "real_balance": real_balance
    })

@app.route('/api/control', methods=['POST'])
def control_bot():
    data = request.json
    action = data.get('action')
    
    running, pid = is_bot_running()
    
    if action == 'start':
        if running:
            return jsonify({"status": "error", "message": "Bot is already running"})
        
        # Start the bot
        try:
            # Run in background, detached
            # Using nohup to keep it running
            # We must use the python executable that has the dependencies installed
            # Assuming 'python3' is the correct one in this env
            cmd = f'nohup python3 "{MAIN_SCRIPT}" > "{LOG_FILE}" 2>&1 & echo $!'
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=BASE_DIR)
            stdout, stderr = process.communicate()
            
            # The pid is printed to stdout because of 'echo $!'
            # But live_trading_bot.py should also write to PID_FILE
            
            # Let's wait a moment for PID file creation
            time.sleep(2)
            
            return jsonify({"status": "success", "message": "Bot started"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    elif action == 'stop':
        if not running:
            return jsonify({"status": "error", "message": "Bot is not running"})
        
        try:
            os.kill(pid, signal.SIGTERM)
            # Clean up PID file if it exists (bot should do it, but just in case)
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return jsonify({"status": "success", "message": "Bot stopped"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    return jsonify({"status": "error", "message": "Invalid action"})

@app.route('/api/logs')
def get_logs():
    logs = ""
    if os.path.exists(LOG_FILE):
        try:
            # Read all lines and join them into a single string
            with open(LOG_FILE, 'r') as f:
                logs = ' '.join([line.strip() for line in f.readlines()])
        except Exception as e:
            logs = f"Error reading logs: {e}"
    else:
        logs = "No logs found."
        
    return jsonify({"logs": logs})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
