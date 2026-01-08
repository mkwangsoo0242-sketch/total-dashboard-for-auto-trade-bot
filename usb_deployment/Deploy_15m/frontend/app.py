from flask import Flask, jsonify, render_template, request
import os
import json
import time
import subprocess
import signal
import ccxt
app = Flask(__name__)

# Base directory where main.py is located (one level up)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(BASE_DIR, 'bot.log')
STATE_FILE = os.path.join(BASE_DIR, 'paper_trade_state.json')
PID_FILE = os.path.join(BASE_DIR, 'bot.pid')
MAIN_SCRIPT = os.path.join(BASE_DIR, 'main.py')

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
        # Load .env manually if exists (simple parsing)
        env_path = os.path.join(BASE_DIR, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, val = line.split('=', 1)
                        # Remove quotes if present
                        val = val.strip('\'"')
                        os.environ[key] = val

        # Try to get keys from env
        api_key = os.getenv('BYBIT_API_KEY', '')
        api_secret = os.getenv('BYBIT_API_SECRET', '')
        
        # Fallback to config.json if not in env
        if not api_key:
            config_path = os.path.join(BASE_DIR, 'config.json')
            if os.path.exists(config_path):
                 with open(config_path, 'r') as f:
                    config = json.load(f)
                    exch_conf = config.get('exchange', {})
                    k = exch_conf.get('api_key')
                    if k and k != 'ENV_VAR':
                        api_key = k
                        api_secret = exch_conf.get('api_secret')

        if api_key and api_secret and api_key != 'ENV_VAR':
            exchange = ccxt.bybit({
                'apiKey': api_key,
                'secret': api_secret,
                'options': {'defaultType': 'future'},
            })
            balance_data = exchange.fetch_balance()
            usdt = balance_data['total'].get('USDT', 0.0)
            
            cached_balance = {
                "balance": float(usdt),
                "currency": "USDT",
                "timestamp": time.time()
            }
        else:
            cached_balance["currency"] = "USDT" # Default to USDT even if no keys
            
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
            
    # 2. Check for any running main.py process using pgrep
    # This catches orphaned processes
    try:
        # Find process IDs for "python3 main.py"
        # -f matches full command line
        result = subprocess.check_output(['pgrep', '-f', 'python3.*main.py'])
        pids = [int(p) for p in result.split()]
        if pids:
            # If we found one, return the first one
            return True, pids[0]
    except subprocess.CalledProcessError:
        # No process found
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
    action = request.json.get('action')
    running, pid = is_bot_running()
    
    if action == 'start':
        if running:
            return jsonify({"status": "error", "message": "Bot is already running"}), 400
        
        # Start bot in background
        try:
            # Using nohup via subprocess to ensure it keeps running
            # We don't need to capture output here as main.py writes to bot.log
            subprocess.Popen(['python3', MAIN_SCRIPT], cwd=BASE_DIR)
            return jsonify({"status": "success", "message": "Bot started"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
            
    elif action == 'stop':
        if not running:
            # Even if not "running" according to is_bot_running (maybe race condition),
            # try to force kill any main.py just in case
            try:
                subprocess.run(['pkill', '-f', 'python3.*main.py'])
                if os.path.exists(PID_FILE):
                    os.remove(PID_FILE)
            except:
                pass
            return jsonify({"status": "error", "message": "Bot is not running (checked)"}), 400
            
        try:
            # 1. Kill specific PID if known
            if pid:
                os.kill(pid, signal.SIGTERM)
            
            # 2. Force kill all main.py instances to be safe
            subprocess.run(['pkill', '-f', 'python3.*main.py'])
            
            # Clean up PID file
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return jsonify({"status": "success", "message": "Bot stopped"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
            
    return jsonify({"status": "error", "message": "Invalid action"}), 400

@app.route('/api/logs')
def get_logs():
    if not os.path.exists(LOG_FILE):
        return jsonify({'logs': ["Log file not found."]}), 404
        
    try:
        # Read the last 100 lines of the log file
        # Using a simple approach: read all and take last 100. 
        # For huge files, seek() is better, but 100 lines is small.
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
            # Return last 50 lines
            last_lines = lines[-50:]
            
            # Remove newlines and reverse order (newest first)
            cleaned_lines = [line.rstrip() for line in last_lines]
            cleaned_lines.reverse()
            
            return jsonify({'logs': cleaned_lines})
    except Exception as e:
        return jsonify({'logs': [f"Error reading log: {str(e)}"]}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
