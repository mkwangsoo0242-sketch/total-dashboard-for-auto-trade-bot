import os
import sys
import threading
import time
import importlib.util
import logging
import pandas as pd
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import uvicorn
import ccxt

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotManager")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()
templates = Jinja2Templates(directory="templates")

class PlaceholderBot:
    def __init__(self, name, interval):
        self.name = name
        self.interval = interval
        self.status = "Stopped"
        self.current_balance = 0.0
        self.current_position = "None"
        self.total_roi = 0.0
        self.recent_candles = []
        self.is_running = False
        self.thread = None
        # Mock data for immediate display
        now = int(time.time() * 1000)
        self.recent_candles = [{'x': now - i*300000, 'y': [90000, 90100, 89900, 90050]} for i in range(50)][::-1]

    def start(self): 
        self.is_running = True
        self.status = "Running"
    
    def stop(self):
        self.is_running = False
        self.status = "Stopped"

class BotManager:
    def __init__(self):
        self.bots = {}
        self.current_price = 90000.0
        self.setup_bots()
        # Initialize data immediately in background
        threading.Thread(target=self.initialize_data, daemon=True).start()
        # Start background price updater
        threading.Thread(target=self.price_updater, daemon=True).start()

    def price_updater(self):
        """Fetch real-time BTC price in background loop."""
        exchange = ccxt.binance()
        while True:
            try:
                ticker = exchange.fetch_ticker('BTC/USDT')
                self.current_price = float(ticker['last'])
            except Exception as e:
                logger.error(f"Price update error: {e}")
            time.sleep(1) # Refresh every 1 second

    def setup_bots(self):
        # 1. 30분봉
        try:
            path = os.path.join(BASE_DIR, "BTC_30분봉_Live")
            sys.path.insert(0, path)
            from BTC_30분봉_Live.live_bot import BinanceLiveBot
            self.bots["Bot_30M"] = BinanceLiveBot()
            self.bots["Bot_30M"].mode = 'paper' 
        except Exception as e:
            logger.error(f"Failed to load Bot_30M: {e}")
            self.bots["Bot_30M"] = PlaceholderBot("Bot_30M", "30m")
        self.bots["Bot_30M"].interval = "30m"

        # 2. 5분봉
        try:
            path = os.path.join(BASE_DIR, "RealTradingBot_Deployment(5분봉)")
            if path not in sys.path: sys.path.insert(0, path)
            import live_trading_bot
            self.bots["Bot_5M"] = live_trading_bot.LiveTradingBot()
            self.bots["Bot_5M"].mode = 'paper'
        except Exception as e:
            logger.error(f"Failed to load Bot_5M: {e}")
            self.bots["Bot_5M"] = PlaceholderBot("Bot_5M", "5m")
        self.bots["Bot_5M"].interval = "5m"

        # 3. 1시간봉
        try:
            path_1h = os.path.join(BASE_DIR, "bybit_bot_usb(1시간-통합)")
            logger.info(f"Loading Bot_1H from {path_1h}")
            spec = importlib.util.spec_from_file_location("final_bot_1h", os.path.join(path_1h, "final_bot_1h.py"))
            mod = importlib.util.module_from_spec(spec)
            sys.modules["final_bot_1h"] = mod # 모듈 등록
            spec.loader.exec_module(mod)
            self.bots["Bot_1H"] = mod.FinalBot1H()
            
            # Monkey Patch to capture candles
            original_fetch = self.bots["Bot_1H"].fetch_data
            def patched_fetch():
                df = original_fetch()
                if df is not None and not df.empty:
                    self.bots["Bot_1H"].recent_candles = [
                        {'x': int(row['timestamp']), 'y': [row['open'], row['high'], row['low'], row['close']]}
                        for _, row in df.tail(100).iterrows()
                    ]
                return df
            self.bots["Bot_1H"].fetch_data = patched_fetch
            
        except Exception as e:
            logger.error(f"Failed to load Bot_1H: {e}")
            self.bots["Bot_1H"] = PlaceholderBot("Bot_1H", "1h")
        self.bots["Bot_1H"].interval = "1h"

        # 4. 15분봉
        try:
            path_15m = os.path.join(BASE_DIR, "deploy_package--15분봉")
            if path_15m not in sys.path: sys.path.insert(0, path_15m)
            import main as bot_15m
            self.bots["Bot_15M"] = bot_15m.dashboard
        except Exception as e:
            logger.error(f"Failed to load Bot_15M: {e}")
            self.bots["Bot_15M"] = PlaceholderBot("Bot_15M", "15m")
        self.bots["Bot_15M"].interval = "15m"

    def initialize_data(self):
        """Pre-populate data for all bots to avoid empty charts."""
        time.sleep(2) # Wait for imports and startups
        logger.info("Initializing bot data...")
        
        # Bot 30M
        try:
            if hasattr(self.bots["Bot_30M"], 'execute_logic'):
                logger.info("Triggering Bot_30M logic for initial data...")
                self.bots["Bot_30M"].execute_logic()
        except Exception as e: logger.error(f"Bot_30M init error: {e}")

        # Bot 1H
        try:
            if hasattr(self.bots["Bot_1H"], 'fetch_data'):
                logger.info("Triggering Bot_1H fetch for initial data...")
                self.bots["Bot_1H"].fetch_data()
        except Exception as e: logger.error(f"Bot_1H init error: {e}")

        # Bots 5M and 15M usually self-init or we can add logic if needed
        logger.info("Data initialization complete.")


    def start_bot(self, name):
        bot = self.bots.get(name)
        if not bot: return
        
        if getattr(bot, 'is_running', False): return

        bot.is_running = True
        bot.status = "실행 중"
        
        # 15분봉 특수 처리
        if name == "Bot_15M":
            import main
            t = threading.Thread(target=main.main, daemon=True)
            bot.thread = t
            t.start()
            return

        # 실행 메서드 찾기
        target = getattr(bot, 'run', getattr(bot, 'start', None))
        if target:
            t = threading.Thread(target=target, daemon=True)
            bot.thread = t
            t.start()
            logger.info(f"Started {name}")
        else:
            logger.error(f"No run/start method for {name}")

    def stop_bot(self, name):
        bot = self.bots.get(name)
        if not bot: return
        
        bot.is_running = False
        bot.status = "Stopped"
        if hasattr(bot, 'stop'): bot.stop()
        logger.info(f"Stopped {name}")

manager = BotManager()

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

import ccxt

@app.get("/api/data")
async def get_data():
    bot_list = []
    total = 0
    
    # 1. Fetch Global Real Price ONCE (Cached)
    real_price = manager.current_price
    if real_price <= 0: real_price = 90000.0

    # 순서 고정
    for name in ["Bot_30M", "Bot_5M", "Bot_1H", "Bot_15M"]:
        bot = manager.bots.get(name)
        if not bot: continue
        
        # 잔고 안전하게 가져오기
        balance = getattr(bot, 'current_balance', 0.0)
        if isinstance(balance, dict):
            balance = balance.get('USDT', {}).get('total', 0.0) if 'USDT' in balance else 0.0
        
        total += float(balance) if isinstance(balance, (int, float)) else 0.0

        # 캔들 데이터 가져오기 (없으면 빈 리스트)
        candles = getattr(bot, 'recent_candles', [])
        
        # *** FORCE SYNC LAST CANDLE ***
        if candles and len(candles) > 0:
            last_candle = candles[-1]
            try:
                # Assuming candle format is {'x': ts, 'y': [open, high, low, close]}
                # Force Close to be real_price
                original_open = last_candle['y'][0]
                
                # Update Close
                last_candle['y'][3] = real_price
                
                # Update High/Low to encompass the new Close
                if real_price > last_candle['y'][1]:
                    last_candle['y'][1] = real_price
                if real_price < last_candle['y'][2]:
                    last_candle['y'][2] = real_price
                
                # In place modification works because it's a reference list/dict
            except Exception as e:
                logger.error(f"Error syncing candle for {name}: {e}")

        # 포지션 정보
        pos = getattr(bot, 'current_position', "None")
        if pos is None: pos = "None"

        current_roi = getattr(bot, 'total_roi', 0.0)

        # 진입 가격 정보
        entry_price = getattr(bot, 'entry_price', 0.0)
        
        # SL 및 청산가 정보 (속성명 통일 시도)
        sl_price = getattr(bot, 'sl_price', getattr(bot, 'stop_price', 0.0))
        liq_price = getattr(bot, 'liquidation_price', 0.0)

        bot_list.append({
            "name": name,
            "interval": getattr(bot, 'interval', '-'),
            "status": getattr(bot, 'status', 'Stopped'),
            "current_balance": balance,
            "current_position": str(pos),
            "entry_price": entry_price,
            "sl_price": sl_price,
            "liq_price": liq_price,
            "total_roi": current_roi,
            "candles": candles,
            "last_update": getattr(bot, 'last_run', datetime.now()).strftime("%H:%M:%S") if isinstance(getattr(bot, 'last_run', None), datetime) else datetime.now().strftime("%H:%M:%S")
        })
        
    return JSONResponse(content={"total_balance": total, "bots": bot_list})

@app.post("/api/bot/start/{name}")
async def start_bot_api(name: str):
    manager.start_bot(name)
    return {"success": True}

@app.post("/api/bot/stop/{name}")
async def stop_bot_api(name: str):
    manager.stop_bot(name)
    return {"success": True}

if __name__ == "__main__":
    # 서버 시작 시 모든 봇 자동 실행
    logger.info("Auto-starting all bots...")
    for name in manager.bots:
        manager.start_bot(name)
        
    uvicorn.run(app, host="0.0.0.0", port=8000)
