import os
import sys
import threading
import time
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# 봇 임포트를 위한 경로 추가
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, 'BTC_30분봉_Live'))
sys.path.append(os.path.join(BASE_DIR, 'RealTradingBot_Deployment(5분봉)'))
sys.path.append(os.path.join(BASE_DIR, 'bybit_bot_usb(1시간-통합)'))
sys.path.append(os.path.join(BASE_DIR, 'deploy_package--15분봉'))

from bots.base_bot import BaseBot
# 각 봇의 실제 클래스 임포트 (수정된 파일 기준)
try:
    from live_bot import BinanceLiveBot
    from live_trading_bot import LiveTradingBot
    from live_trader_bybit import LiveTrader
except ImportError as e:
    print(f"임포트 오류: {e}. 일부 봇을 로드할 수 없습니다.")

class BotManager:
    def __init__(self):
        self.app = FastAPI()
        self.bots = {}
        self.total_balance_history = []
        self.max_history = 50
        
        # 템플릿 및 정적 파일 설정
        self.templates = Jinja2Templates(directory="templates")
        
        # 봇 초기화
        self.setup_bots()
        self.setup_routes()

    def setup_bots(self):
        """실제 봇 인스턴스 생성"""
        try:
            # 30분봉 봇
            self.bots["Bot_30M"] = BinanceLiveBot()
            # 5분봉 봇
            self.bots["Bot_5M"] = LiveTradingBot()
            # 1시간봉 봇
            self.bots["Bot_1H"] = LiveTrader()
            
            # 15분봉 봇은 main.py 내의 dashboard 객체를 사용
            try:
                import main as bot_15m_main
                self.bots["Bot_15M"] = bot_15m_main.dashboard
            except:
                from bots.trading_bot import TradingBot
                self.bots["Bot_15M"] = TradingBot("Bot_15M", "15m")
            
        except Exception as e:
            print(f"봇 초기화 중 오류 발생: {e}")
            # 폴백: 오류 시 빈 봇 생성
            if not self.bots:
                from bots.trading_bot import TradingBot
                self.bots = {
                    "Bot_5M": TradingBot("Bot_5M", "5m"),
                    "Bot_15M": TradingBot("Bot_15M", "15m"),
                    "Bot_30M": TradingBot("Bot_30M", "30m"),
                    "Bot_1H": TradingBot("Bot_1H", "1h")
                }

    def run_15m_bot(self):
        """15분봉 봇은 main.py의 main() 함수를 실행해야 함"""
        try:
            import main as bot_15m_main
            # dashboard 객체를 공유하기 위해 main.py 수정이 필요할 수 있으나
            # 현재는 별도 실행 후 데이터를 어떻게 가져올지 고민 필요
            # 일단은 run_bot을 직접 호출하는 방식으로 우회
            bot_15m_main.main() 
        except Exception as e:
            print(f"15분봉 봇 실행 오류: {e}")

    def start_bots(self):
        print("모든 봇을 시작합니다...")
        for name, bot in self.bots.items():
            if name == "Bot_15M":
                # 15분봉 봇은 별도 스레드에서 main 실행
                t = threading.Thread(target=self.run_15m_bot, daemon=True)
            else:
                t = threading.Thread(target=bot.run, daemon=True)
            t.start()
            print(f"{name} 시작됨.")



    def update_total_history(self):
        while True:
            total = sum(bot.current_balance for bot in self.bots.values())
            if total > 0:
                self.total_balance_history.append(total)
                if len(self.total_balance_history) > self.max_history:
                    self.total_balance_history.pop(0)
            time.sleep(2)

    def _extract_bot_data(self, bot):
        """봇 상태 데이터 안전 추출"""
        from datetime import datetime
        
        data = {
            "name": getattr(bot, 'name', 'Unknown'),
            "interval": getattr(bot, 'interval', 'Unknown'),
            "status": getattr(bot, 'status', 'Stopped'),
            "current_balance": getattr(bot, 'current_balance', 0.0),
            "history": getattr(bot, 'balance_history', []),
            "candles": getattr(bot, 'recent_candles', []),
            "total_roi": getattr(bot, 'total_roi', 0.0),
            "liquidation_price": getattr(bot, 'liquidation_price', 0.0),
            "liquidation_profit": getattr(bot, 'liquidation_profit', 0.0),
            "last_update": getattr(bot, 'last_run', None).strftime('%H:%M:%S') if getattr(bot, 'last_run', None) else '-',
        }

        # 포지션 정보 정규화
        raw_pos = getattr(bot, 'current_position', None)
        entry = 0.0
        sl = 0.0
        pos_str = "None"
        
        # 1. 속성으로 존재하는 경우 (30m 등)
        entry = getattr(bot, 'entry_price', 0.0)
        sl = getattr(bot, 'stop_loss', getattr(bot, 'stop_price', 0.0))

        # 2. 딕셔너리로 존재하는 경우 (5m, 1h 등)
        if isinstance(raw_pos, dict):
            # Entry
            if entry == 0:
                entry = float(raw_pos.get('entry', raw_pos.get('entry_price', 0)))
            
            # SL
            if sl == 0:
                sl = float(raw_pos.get('sl', raw_pos.get('stop_loss', 0)))
                
            # String Formatting
            type_side = raw_pos.get('type', raw_pos.get('side', ''))
            amt = raw_pos.get('amount', raw_pos.get('qty', raw_pos.get('contracts', 0)))
            if type_side:
                pos_str = f"{type_side.upper()} ({amt})"
            else:
                pos_str = "None"
        
        # 3. 문자열인 경우
        elif isinstance(raw_pos, str):
            pos_str = raw_pos
            
        data['entry_price'] = entry
        data['stop_loss'] = sl
        data['current_position'] = pos_str
        
        return data

    def setup_routes(self):
        @self.app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            return self.templates.TemplateResponse("index.html", {"request": request})

        @self.app.post("/api/bot/{bot_name}/start")
        async def start_bot(bot_name: str):
            if bot_name not in self.bots:
                return {"status": "error", "message": "Bot not found"}
            
            bot = self.bots[bot_name]
            
            try:
                # Thread checking is tricky, assume boolean flag is source of truth
                is_running = getattr(bot, 'is_running', False)
                if is_running:
                     return {"status": "error", "message": "Already running"}

                target = None
                if bot_name == "Bot_15M":
                    target = self.run_15m_bot
                else:
                    target = bot.run
                    
                t = threading.Thread(target=target, daemon=True)
                t.start()
                
                # Flag set
                bot.is_running = True
                # Optional: Update status text immediately
                bot.status = "Starting..."
                    
                return {"status": "success", "message": f"{bot_name} started"}
            except Exception as e:
                 return {"status": "error", "message": str(e)}

        @self.app.post("/api/bot/{bot_name}/stop")
        async def stop_bot(bot_name: str):
            if bot_name not in self.bots:
                return {"status": "error", "message": "Bot not found"}
            
            bot = self.bots[bot_name]
            try:
                if hasattr(bot, 'stop'):
                    bot.stop()
                else:
                    bot.is_running = False
                    bot.status = "Stopping..."
                    
                return {"status": "success", "message": f"{bot_name} stopped"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self.app.get("/api/data")
        async def get_data():
            bot_data = []
            for name, bot in self.bots.items():
                b_data = self._extract_bot_data(bot)
                b_data['name'] = name # Override name key with dict key just in case
                bot_data.append(b_data)
            
            return {
                "total_balance": sum(bot.current_balance for bot in self.bots.values()),
                "total_history": self.total_balance_history,
                "bots": bot_data
            }

    def run_web_server(self):
        uvicorn.run(self.app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    manager = BotManager()
    
    # 봇 시작
    manager.start_bots()
    
    # 히스토리 업데이트 스레드 시작
    history_thread = threading.Thread(target=manager.update_total_history, daemon=True)
    history_thread.start()
    
    # 웹 서버 실행
    manager.run_web_server()
