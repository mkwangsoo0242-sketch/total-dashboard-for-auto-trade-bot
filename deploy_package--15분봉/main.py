import ccxt
import json
import time
import schedule
import pandas as pd
import os
import sys
import logging
from datetime import datetime

# BaseBot 임포트를 위한 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bots.base_bot import BaseBot

# Define Base Directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from market_analyzer import MarketAnalyzer
from strategy_15m import Strategy
from paper_trader import PaperTrader

# Setup Logging
# ANSI Colors for Terminal
class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m" # Might be hard on white, but standard
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    BOLD = "\033[1m"

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        
        # Only colorize if it looks like our status line
        if "Price:" in msg:
            msg = msg.replace("Price:", f"{Colors.YELLOW}{Colors.BOLD}Price:{Colors.RESET}")
            msg = msg.replace("RSI2:", f"{Colors.MAGENTA}RSI2:{Colors.RESET}")
            msg = msg.replace("Trend: UP", f"Trend: {Colors.GREEN}{Colors.BOLD}UP{Colors.RESET}")
            msg = msg.replace("Trend: DOWN", f"Trend: {Colors.RED}{Colors.BOLD}DOWN{Colors.RESET}")
            
            if "No signal" in msg:
                msg = msg.replace("No signal", f"{Colors.RESET}No signal")
            elif "SIGNAL:" in msg:
                 msg = msg.replace("!!! SIGNAL:", f"{Colors.RED}{Colors.BOLD}!!! SIGNAL:{Colors.RESET}")
        
        return msg

# Configure Logging
# Remove all existing handlers to prevent duplicates or old configs
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 1. File Handler (NO Color - Plain Text)
file_handler = logging.FileHandler(os.path.join(BASE_DIR, "bot.log"))
file_formatter = logging.Formatter('%(asctime)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# 2. Console Handler (Colored) - Commented out for now
# console_handler = logging.StreamHandler()
# console_formatter = ColoredFormatter(f'{Colors.CYAN}%(asctime)s{Colors.RESET} - %(message)s')
# console_handler.setFormatter(console_formatter)
# logger.addHandler(console_handler)

def load_env(filepath=None):
    """Simple .env loader to avoid dependencies"""
    if filepath is None:
        filepath = os.path.join(BASE_DIR, '.env')

    try:
        with open(filepath) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
        logging.info("Loaded .env file")
    except FileNotFoundError:
        logging.error(".env file not found")

def run_bot(exchange, analyzer, strategy, config, paper_trader=None, dashboard=None):
    # logging.info("Scanning market...\") # Reduced log noise
    
    try:
        from datetime import datetime
        if dashboard:
            dashboard.last_run = datetime.now()
        
        # 1. Fetch Data
        df = analyzer.fetch_ohlcv(limit=300) # Enough for EMA200
        if df is None:
            logging.error("Failed to fetch data")
            return

        # 2. Analyze Indicators
        df = analyzer.analyze(df)
        curr_price = df.iloc[-1]['close']
        
        # update dashboard candles
        if dashboard:
             # Assuming index is timestamp or there is a 'timestamp' column. 
             # If `analyzer` returns df with 'timestamp' column or index, we need to adapt.
             # Checking `main.py` alone is hard, but usually index.
             # Let's try to infer from typical usage. 
             # I'll iterate last 100 rows.
             candles = []
             # If index is datetime, convert to int timestamp
             for idx, row in df.tail(100).iterrows():
                 ts = idx.timestamp() * 1000 if isinstance(idx, pd.Timestamp) else idx
                 candles.append({
                     'x': int(ts), 
                     'y': [row['open'], row['high'], row['low'], row['close']]
                 })
             dashboard.recent_candles = candles
        
        # Update Paper Trader Positions (Check SL/TP)
        if paper_trader:
            paper_trader.update(curr_price)
        
        # 3. Check Signal
        signal = strategy.check_entry(df)
        
        rsi_val = df.iloc[-1]['rsi_2']
        trend_status = 'UP' if df.iloc[-1]['close'] > df.iloc[-1]['ema_200'] else 'DOWN'
        
        log_msg = f"Price: {curr_price:.2f} | RSI2: {rsi_val:.2f} | Trend: {trend_status}"
        
        if signal:
            logging.info(f"{log_msg} | !!! SIGNAL: {signal} !!!")
            
            # In Dry Run, we just calculate potential SL/TP
            sl, tp = strategy.calculate_stops(df, signal, curr_price)
            logging.info(f"Entry: {curr_price} | SL: {sl:.2f} | TP: {tp:.2f}")
            
            if not config['system']['dry_run']:
                # execute_trade(signal, sl, tp)
                pass
            elif paper_trader:
                # Execute Paper Trade
                paper_trader.open_position(signal, curr_price, sl, tp)
            else:
                logging.info("Dry Run - No trade")
        else:
            logging.info(f"{log_msg} | No signal")
            
        # 대시보드 업데이트
        if dashboard:
            balance = 0
            if paper_trader:
                balance = paper_trader.balance
            else:
                try:
                    balance_data = exchange.fetch_balance()
                    balance = balance_data['total'].get('USDT', 0.0)
                except: pass
            
            dashboard.current_balance = balance
            dashboard.status = "실행 중" if not signal else f"{signal} 시그널"
            
            # Check for generic position if possible, though main.py structure is slightly different.
            if paper_trader and paper_trader.position:
                entry = paper_trader.position.get('entry_price', 0)
                sl = paper_trader.position.get('sl', 0)
                # side = paper_trader.position.get('side', 'unknown').upper()
                
                dashboard.status = "실행 중" # Always "실행 중"
                dashboard.entry_price = entry
                dashboard.sl_price = sl
                dashboard.liq_price = 0 # Not currently simulated in 15m paper trader
            else:
                 dashboard.entry_price = 0
                 dashboard.sl_price = 0
                 dashboard.liq_price = 0
            dashboard.balance_history.append(balance)
            if len(dashboard.balance_history) > dashboard.max_history:
                dashboard.balance_history.pop(0)

    except Exception as e:
        logging.error(f"Error in bot loop: {e}")

# Initialize Dashboard (모듈 수준에서 공유)
from bots.trading_bot import TradingBot
dashboard = TradingBot(name="Bot_15M", interval="15m")

def main():
    # Write PID to file
    pid = os.getpid()
    pid_file = os.path.join(BASE_DIR, 'bot.pid')
    with open(pid_file, 'w') as f:
        f.write(str(pid))
        
    def cleanup_pid():
        if os.path.exists(pid_file):
            os.remove(pid_file)
            
    import atexit
    atexit.register(cleanup_pid)
        
    print("Starting High Profit Bot (Survival Mode 163x)...")
    
    # Load environment variables
    load_env()

    try:
        config_path = os.path.join(BASE_DIR, 'config.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Config file not found at {config_path}!")
        return

    # Initialize Exchange
    exchange_config = {
        'apiKey': os.getenv('BYBIT_API_KEY', config['exchange']['api_key']).strip(),
        'secret': os.getenv('BYBIT_API_SECRET', config['exchange']['api_secret']).strip(),
        'options': {'defaultType': 'future'},
        'enableRateLimit': True
    }
    
    try:
        exchange = getattr(ccxt, config['exchange']['name'])(exchange_config)
    except Exception as e:
        logging.error(f"Failed to initialize exchange: {e}")
        return

    # Init Modules
    analyzer = MarketAnalyzer(exchange, config)
    strategy = Strategy(config)
    
    # Initialize Paper Trader if in Dry Run mode
    paper_trader = None
    if config['system']['dry_run']:
        logging.info("Initializing Paper Trader...")
        paper_trader = PaperTrader(config)
    
    logging.info(f"Loaded Configuration:")
    logging.info(f"Leverage: {config['exchange']['leverage']}x")
    logging.info(f"Risk: {config['risk']['risk_per_trade_percent']}%")
    logging.info(f"Strategy: {config['strategy']['name']} (RSI2 + Trend Filter)")
    logging.info("-" * 50)

    global dashboard
    dashboard.status = "초기화 중"
    dashboard.is_running = True

    # Schedule Job
    # Run every 10 seconds
    schedule.every(10).seconds.do(run_bot, exchange, analyzer, strategy, config, paper_trader, dashboard)
    
    # Run once immediately
    run_bot(exchange, analyzer, strategy, config, paper_trader, dashboard)
    
    # Initial Real Balance Fetch
    fetch_and_save_real_balance(exchange)

    while dashboard.is_running:
        schedule.run_pending()
        time.sleep(1)
        
    logging.info("15M Bot Stopped.")
    dashboard.status = "Stopped"

def fetch_and_save_real_balance(exchange):
    try:
        balance_data = exchange.fetch_balance()
        usdt_balance = balance_data['total'].get('USDT', 0.0)
        
        real_balance_file = os.path.join(BASE_DIR, 'real_balance.json')
        with open(real_balance_file, 'w') as f:
            json.dump({"balance": usdt_balance, "currency": "USDT", "updated_at": datetime.now().isoformat()}, f)
            
    except Exception as e:
        logging.error(f"Failed to fetch real balance: {e}")

if __name__ == "__main__":
    main()
