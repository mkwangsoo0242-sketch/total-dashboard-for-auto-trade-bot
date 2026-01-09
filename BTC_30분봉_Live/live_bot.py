import ccxt
import random
import pandas as pd
import time
import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv
from strategy_30m import Strategy30m

# BaseBot 임포트를 위한 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bots.base_bot import BaseBot

# 로그 설정 (전용 핸들러 사용으로 격리)

log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, 'bot.log')

print("Executing live_bot.py module level code.")
logger = logging.getLogger("BTC_30M_Bot")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
if not logger.handlers:
    fh = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(sh)
    logger.propagate = False

    fh = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
logger.info(f"Log file path: {log_file}")

logger.info("Initializing BTC_30M_Bot process...")
logger.info("30분봉 (30m) 트레이딩 봇 로드 중...")

# .env 파일에서 설정 로드
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path)

class BinanceLiveBot(BaseBot):
    def __init__(self):
        super().__init__(name="Bot_30M", interval="30m")
        self.mode = os.getenv('TRADING_MODE', 'paper').lower()
        
        # 가상 거래 상태 변수
        self.paper_balance = 100.0
        self.paper_pos_size = 0.0
        self.paper_entry_price = 0.0
        
        # API Keys
        self.api_key = os.getenv('BYBIT_API_KEY_30M') or os.getenv('BYBIT_API_KEY') or os.getenv('BINANCE_API_KEY')
        self.api_secret = os.getenv('BYBIT_SECRET_30M') or os.getenv('BYBIT_SECRET_KEY') or os.getenv('BYBIT_SECRET') or os.getenv('BINANCE_SECRET')
        self.log(f"TRADING_MODE: {self.mode}")
        if self.mode != 'paper':
            if not self.api_key or not self.api_secret:
                self.log("ERROR: API_KEY or API_SECRET is missing for live trading mode. Please check your .env file (BYBIT_API_KEY, BYBIT_SECRET).")
                raise ValueError("API_KEY and API_SECRET must be set for live trading.")
            self.log(f"API Key (first 5 chars): {self.api_key[:5]}*****")
            self.log(f"API Secret (first 5 chars): {self.api_secret[:5]}*****")
        else:
            self.log("Running in paper mode. API keys are not used for exchange connection.")

        self.symbol = 'BTC/USDT' # Bybit format might need checking but BTC/USDT usually works with defaultType future
        self.timeframe = '30m'
        
        # Bybit Exchange Setup
        exchange_config = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'options': {'defaultType': 'future'}, # Bybit uses 'future' or 'swap' for linear perps
            'enableRateLimit': True,
        }
        if self.mode == 'paper':
            exchange_config['apiKey'] = None
            exchange_config['secret'] = None
            
        if self.mode != 'paper':
            self.exchange = ccxt.bybit(exchange_config)
        else:
            class MockExchange:
                def __getattr__(self, name):
                    raise NotImplementedError(f"CCXT method '{name}' called in paper mode without proper mocking. Check 'if self.mode == \"paper\"' guards.")
            self.exchange = MockExchange()
        self.strat = Strategy30m(initial_leverage=10, mode='extreme_growth')
        
        # Trading State Attributes
        self.current_position = None # 'long', 'short', None
        self.entry_price = 0
        self.total_position_size = 0
        self.stop_price = 0
        self.peak_price = 0
        self.trade_leverage = 10
        self.partial_hits = {'0': False, '1': False, '2': False}
        
        logger.info(f"봇 초기화 완료: BTC/USDT (30m). Mode: {self.mode}, Exchange type: {type(self.exchange).__name__} (Bybit)")

    def log(self, message):
        logger.info(message)

    def run(self):
        """메인 실행 루프"""
        self.log(f"🚀 Bot started... Waiting for next candle.")
        self.status = "실행 중"
        while self.is_running:
            try:
                self.last_run = datetime.now()
                self.execute_logic()
                time.sleep(1)
            except Exception as e:
                self.log(f"Error in main loop: {e}")
                time.sleep(5)

    def execute_logic(self):
        try:
            self.sync_position()
            
            # --- Data Fetching Logic (Unified) ---
            if self.mode != 'paper':
                ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
            else:
                # Paper trading mode: Use REAL data for chart, but don't trade on exchange
                # self.log("Paper trading mode: Fetching REAL OHLCV data from Bybit.")
                try:
                    # Fetch real data using a temporary public instance
                    public_exchange = ccxt.bybit()
                    ohlcv = public_exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                except Exception as e:
                    self.log(f"Error fetching real data in paper mode: {e}")
                    ohlcv = []
                    # Fallback to single candle if fetch fails
                    price = 90000.0
                    mock_timestamp = int(datetime.datetime.now().timestamp() * 1000)
                    ohlcv = [[mock_timestamp, price, price, price, price, 0]]
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)

            self.recent_candles = [
                {'x': int(row.name.timestamp() * 1000), 
                 'y': [row['open'], row['high'], row['low'], row['close']]}
                for idx, row in df.tail(100).iterrows()
            ]
            
            df_with_ind = self.strat.populate_indicators(df)
            curr = df_with_ind.iloc[-1]
            current_price = curr['close']
            balance = self.get_balance()
            
            # Monitoring fields update
            self.current_balance = balance
            self.status = "실행 중"
            # if self.current_position:
            #    pass # Status remains "실행 중"
            # else:
            #    pass
            
            # self.log(f"Current Price: {current_price:,.1f} | Pos: {str(self.current_position).upper()} | Balance: {balance:.2f} USDT")

            # 3. 매매 전략 판정
            if hasattr(self.strat, 'get_current_signal'):
                signal_data = self.strat.get_current_signal(df_with_ind)
            else:
                # Fallback Signal Logic (Simple Donchian)
                d_high = curr.get('donchian_high')
                d_low_entry = curr.get('donchian_low_entry')
                
                action = None
                if d_high is not None and current_price > d_high:
                    action = 'long'
                elif d_low_entry is not None and current_price < d_low_entry:
                    action = 'short'
                
                signal_data = {
                    'action': action,
                    'leverage': 10,
                    'risk_pct': 0.1,
                    'stop_atr': 3.0,
                    'donchian_low': curr.get('donchian_low'),
                    'is_strong_bull': False
                }

            # 4. 진입/종료 로직 실행
            self.trade_strategy(curr, signal_data)
            
        except Exception:
            import traceback
            self.log(f"execute_logic 오류 상세:\n{traceback.format_exc()}")

    def get_balance(self):
        if self.mode == 'paper':
            return self.paper_balance
        try:
            balance = self.exchange.fetch_balance()
            return float(balance['total']['USDT'])
        except Exception as e:
            self.log(f"잔고 조회 오류: {e}")
            return 0.0

    def sync_position(self):
        # self.log(f"DEBUG: Entering sync_position. Mode: {self.mode}, Exchange type: {type(self.exchange).__name__}")
        if self.mode == 'paper':
            # self.log("DEBUG: Paper mode detected in sync_position. Using paper position data.")
            if self.paper_pos_size > 1e-8:
                self.current_position, self.total_position_size, self.entry_price = 'long', self.paper_pos_size, self.paper_entry_price
            elif self.paper_pos_size < -1e-8:
                self.current_position, self.total_position_size, self.entry_price = 'short', abs(self.paper_pos_size), self.paper_entry_price
            else:
                self.current_position, self.total_position_size, self.entry_price = None, 0, 0
            return
        else:
            # self.log(f"DEBUG: Live mode detected in sync_position. Attempting to fetch positions from real exchange.")
            try:
                positions = self.exchange.fetch_positions([self.symbol])
                for pos in positions:
                    if pos['symbol'].replace('/', '') == 'BTCUSDT':
                        size = float(pos['contracts'])
                        if size != 0:
                            self.current_position = 'long' if size > 0 else 'short'
                            self.total_position_size = abs(size)
                            self.entry_price = float(pos['entryPrice'])
                            return
                self.current_position, self.total_position_size, self.entry_price = None, 0, 0
            except Exception as e:
                self.log(f"포지션 동기화 오류: {e}")

    def trade_strategy(self, curr, signal_data):
        current_price = curr['close']
        balance = self.get_balance()

        # 1. 진입
        if self.current_position is None:
            action = signal_data.get('action')
            if action in ['long', 'short']:
                # 지표 유효성 체크
                d_high = curr.get('donchian_high')
                d_low_entry = curr.get('donchian_low_entry')
                atr = curr.get('atr')
                
                if d_high is None or d_low_entry is None or atr is None:
                    # self.log("지표 데이터 부족으로 진입 대기...")
                    return

                self.trade_leverage = signal_data.get('leverage', 10)
                risk_pct = signal_data.get('risk_pct', 0.1)
                
                self.entry_price = current_price
                
                # SL 계산
                stop_atr_mult = signal_data.get('stop_atr', 3.0)
                if action == 'long':
                    self.stop_price = current_price - (atr * stop_atr_mult)
                    # Donchian Low도 고려 (더 타이트한 것 선택 등) - 여기선 ATR 기준
                else:
                    self.stop_price = current_price + (atr * stop_atr_mult)
                
                side = 'buy' if action == 'long' else 'sell'
                
                stop_dist_pct = abs(self.entry_price - self.stop_price) / self.entry_price
                if stop_dist_pct < 0.005: stop_dist_pct = 0.005
                pos_value = (balance * risk_pct) / stop_dist_pct
                amount = pos_value / self.entry_price
                
                order = self.execute_order(side, amount, current_price)
                if order:
                    self.current_position, self.total_position_size, self.peak_price = action, amount, self.entry_price
                    self.partial_hits = {'0': False, '1': False, '2': False}
                    self.log(f"🚀 {action.upper()} 진입 완료 (가격: {self.entry_price:,.1f}, 수량: {amount:.4f})")

        # 2. 유지 및 종료
        else:
            roi_unleveraged = (current_price - self.entry_price) / self.entry_price if self.current_position == 'long' else (self.entry_price - current_price) / self.entry_price
            leveraged_roi = roi_unleveraged * self.trade_leverage
            
            # --- Trailing Stop & Partial Profit (Simplified for focus) ---
            # ... (전략 로직)
            
            # Exit Check
            should_exit = False
            exit_reason = ""
            
            # Simple Donchian Exit
            donchian_low = curr.get('donchian_low')
            if self.current_position == 'long' and donchian_low and current_price < donchian_low:
                should_exit = True
                exit_reason = "Donchian Low Breakdown"
            
            # SL Check
            if self.current_position == 'long' and current_price < self.stop_price:
                 should_exit = True
                 exit_reason = "Stop Loss"
            elif self.current_position == 'short' and current_price > self.stop_price:
                 should_exit = True
                 exit_reason = "Stop Loss"

            if should_exit:
                side = 'sell' if self.current_position == 'long' else 'buy'
                order = self.execute_order(side, self.total_position_size, current_price)
                if order:
                    self.log(f"👋 포지션 종료: {exit_reason} (ROI: {leveraged_roi*100:.2f}%)")
                    self.current_position = None
                    self.total_position_size = 0

    def execute_order(self, side, amount, price):
        if self.mode == 'paper':
            # 가상 매매 체결
            fee = (price * amount) * 0.0005
            self.paper_balance -= fee
            
            if side == 'buy':
                if self.paper_pos_size < 0: # 숏 청산
                    self.paper_balance += (self.paper_entry_price - price) * abs(self.paper_pos_size)
                    self.paper_pos_size = 0.0
                else: # 롱 진입
                    self.paper_pos_size += amount
                    self.paper_entry_price = price
            else:
                if self.paper_pos_size > 0: # 롱 청산
                    self.paper_balance += (price - self.paper_entry_price) * self.paper_pos_size
                    self.paper_pos_size = 0.0
                else: # 숏 진입
                    self.paper_pos_size -= amount
                    self.paper_entry_price = price
            return True
        
        try:
            self.exchange.set_leverage(int(self.trade_leverage), self.symbol)
            return self.exchange.create_market_order(self.symbol, side, amount)
        except Exception as e:
            self.log(f"주문 실패: {e}")
            return None

if __name__ == "__main__":
    bot = BinanceLiveBot()
    # 단독 실행 시 테스트용
    bot.execute_logic()
