"""
🚀 최종 1시간봉 다중 모델 트레이딩 봇 (Bybit)
- Short/Long/Regime ML 모델 (XGBoost)
- 트레일링 스탑 적용 (수익 극대화)
- 15분봉 성공 전략 이식
"""
import ccxt
import pandas as pd
import numpy as np
import joblib
import os
import time
import logging
import json
import sys
from datetime import datetime
import subprocess
import random
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, 'bot_1h.log')

log_file_obj = open(log_file, 'a', buffering=1)
handler = logging.StreamHandler(log_file_obj)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

logger.debug(f"Logging configured. Log file: {log_file}")

load_dotenv()

class FinalBot1H:
    def __init__(self):
        self.symbol = 'BTC/USDT'
        self.timeframe = '1h'
        self.initial_balance = 100
        self.balance = self.initial_balance
        self.mode = os.getenv('TRADING_MODE', 'paper').lower()
        
        # Dashboard Attributes
        self.is_running = False
        self.status = "Stopped"
        self.current_balance = self.balance
        self.current_position = "None"
        self.total_roi = 0.0
        
        self.load_models()
        
        self.api_key = os.getenv('BYBIT_API_KEY')
        self.secret = os.getenv('BYBIT_API_SECRET')
        
        exchange_config = {
            'apiKey': self.api_key,
            'secret': self.secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        }
        
        if self.mode != 'paper':
            self.exchange = ccxt.bybit(exchange_config)
        else:
            class MockExchange:
                def __init__(self, balance, logger):
                    self.balance = balance
                    self.logger = logger

                def fetch_ohlcv(self, symbol, timeframe, limit):
                    self.logger.info("Paper trading mode: Fetching REAL OHLCV...")
                    try:
                        # Fetch real data using a public instance
                        public_exchange = ccxt.bybit()
                        ohlcv = public_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                        return ohlcv
                    except Exception as e:
                        self.logger.error(f"Error fetching real OHLCV: {e}")
                        # Fallback
                        now = int(time.time() * 1000)
                        return [[now, 90000, 90000, 90000, 90000, 100]] * limit
                
                def fetch_balance(self):
                    self.logger.info("Paper trading mode: Mocking fetch_balance.")
                    return {'total': {'USDT': self.balance}}
                
                def fetch_positions(self, symbols=None):
                    self.logger.info("Paper trading mode: Mocking fetch_positions.")
                    return [] # For simplicity, assume no open positions in mock
                
                def fetch_ohlcv(self, symbol, timeframe, limit):
                    """Fetch real OHLCV data from Bybit for paper trading"""
                    self.logger.info("Paper trading mode: Fetching REAL OHLCV...")
                    try:
                        public_exchange = ccxt.bybit()
                        return public_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                    except Exception as e:
                        self.logger.error(f"Failed to fetch OHLCV: {e}")
                        return None
                
                def create_market_order(self, symbol, side, amount):
                    self.logger.info(f"Paper trading mode: Mocking market order {side} {amount} {symbol}.")
                    # Simulate order execution
                    return {'info': {'status': 'ok'}}
                
                def set_leverage(self, leverage, symbol):
                    self.logger.info(f"Paper trading mode: Mocking set_leverage {leverage} for {symbol}.")
                    return True
                    
                def fetch_ticker(self, symbol):
                    return {'last': 90600} # Mock price for status log
            self.exchange = MockExchange(self.balance, logger)
        
        # 전략 설정 (초공격적 - 4.1억 승리 플랜)
        self.regime_config = {
            0: {'name': 'SIDEWAYS', 'action': 'skip'},
            1: {'name': 'BULL', 'action': 'long', 'risk': 0.08, 'leverage': 25}, 
            2: {'name': 'BEAR', 'action': 'short', 'risk': 0.05, 'leverage': 15}
        }
        self.threshold = 0.52
        
        # 트레일링 스탑 (타이트하게)
        self.use_ts = True
        self.ts_activation = 1.5 
        self.ts_callback = 1.0   
        
        self.position = 0
        self.entry_price = 0
        self.sl_price = 0
        self.tp_price = 0
        self.max_price = 0
        self.min_price = 0
        self.consecutive_losses = 0
        self.rest_until = 0
        
        self.trades = []
        self.state_file = 'bot_1h_state.json'
        self.load_state()
        
        # FORCE RESET BALANCE as per user request
        self.balance = 100
        self.current_balance = 100
        
        logger.info(f"🤖 1시간봉 최종 봇 초기화 완료 (잔고: {self.balance})")

    def start_scheduler(self):
        def job():
            logger.info("⏰ 00:00 정기 재학습 시작...")
            subprocess.Popen([sys.executable, "retrain.py"])
            
        schedule.every().day.at("00:00").do(job)
        
        def run_schedule():
            while True:
                schedule.run_pending()
                time.sleep(60)
                
        t = threading.Thread(target=run_schedule, daemon=True)
        t.start()
        logger.info("📅 자동 재학습 스케줄러 가동 (매일 00:00)")

    def check_model_reload(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, 'xgb_short_1h.pkl')
            mtime = os.path.getmtime(path)
            if mtime > self.model_ts:
                logger.info("🔄 새로운 모델 파일 감지! 다시 로드합니다.")
                self.load_models()
        except: pass

    def load_models(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            short_path = os.path.join(base_dir, 'xgb_short_1h.pkl')
            
            if os.path.exists(short_path):
                self.model_ts = os.path.getmtime(short_path)
            
            self.short_model_data = joblib.load(short_path)
            self.long_model_data = joblib.load(os.path.join(base_dir, 'xgb_long_1h.pkl'))
            self.regime_model_data = joblib.load(os.path.join(base_dir, 'xgb_regime_1h.pkl'))
            
            self.short_model = self.short_model_data['model']
            self.long_model = self.long_model_data['model']
            self.regime_model = self.regime_model_data['model']
            logger.info("✅ ML 모델 로드 성공")
        except Exception as e:
            logger.error(f"❌ 모델 로드 실패: {e}")
            # 모델 로드 실패 시 sys.exit(1) 대신 PlaceholderBot 사용하도록 bot_manager.py에서 처리

    def fetch_data(self):
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=300)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # 지표 계산
            df['ema_20'] = df['close'].ewm(span=20).mean()
            df['ema_60'] = df['close'].ewm(span=60).mean()
            df['ema_200'] = df['close'].ewm(span=200).mean()
            
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            exp12 = df['close'].ewm(span=12, adjust=False).mean()
            exp26 = df['close'].ewm(span=26, adjust=False).mean()
            df['macd'] = exp12 - exp26
            df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
            df['macd_hist'] = df['macd'] - df['macd_signal']
            
            min_val = df['rsi'].rolling(14).min()
            max_val = df['rsi'].rolling(14).max()
            df['stoch_k'] = (df['rsi'] - min_val) / (max_val - min_val) * 100
            
            tr1 = df['high'] - df['low']
            tr2 = abs(df['high'] - df['close'].shift())
            tr3 = abs(df['low'] - df['close'].shift())
            df['atr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()
            
            std = df['close'].rolling(20).std()
            df['bb_upper'] = df['ema_20'] + (std * 2)
            df['bb_lower'] = df['ema_20'] - (std * 2)
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['ema_20']
            
            # Features
            df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
            df['dist_ema60'] = (df['close'] - df['ema_60']) / df['ema_60']
            df['dist_ema200'] = (df['close'] - df['ema_200']) / df['ema_200']
            df['rsi_change'] = df['rsi'].diff()
            df['vol_change'] = df['volume'].pct_change()
            df['macd_hist_change'] = df['macd_hist'].diff()
            
            all_feats = list(set(self.regime_model_data['features'] + self.short_model_data['features'] + self.long_model_data['features']))
            for f in all_feats:
                if f not in df.columns: df[f] = 0
                df[f] = df[f].fillna(0).replace([np.inf, -np.inf], 0)
                
            return df
        except Exception as e:
            import traceback
            logger.error(f"데이터 조회 실패: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def save_state(self):
        state = {
            'balance': self.balance,
            'position': self.position,
            'entry_price': self.entry_price,
            'sl_price': self.sl_price,
            'consecutive_losses': self.consecutive_losses,
            'trades': self.trades[-50:]
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2, default=str)

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                self.balance = state.get('balance', 100)
                self.position = state.get('position', 0)
                self.entry_price = state.get('entry_price', 0)
                self.sl_price = state.get('sl_price', 0)
                self.consecutive_losses = state.get('consecutive_losses', 0)
                self.trades = state.get('trades', [])
                if self.position > 0: self.max_price = self.entry_price
                elif self.position < 0: self.min_price = self.entry_price
            except: pass


    def start(self):
        if not self.is_running:
            self.is_running = True
            self.status = "Running"
            # In a real app, you might want to run this in a thread managed by the caller.
            # Here we assume the caller (bot_manager) invoked start() in a thread.
            try:
                self.run()
            except Exception as e:
                logger.error(f"Bot execution failed: {e}")
                self.is_running = False
                self.status = "Error"

    def stop(self):
        self.is_running = False
        self.status = "Stopped"

    def run(self):
        logger.info("🚀 Bot started... Waiting for next candle.")
        self.status = "Running"
        while self.is_running:
            try:
                # 1. Update Real-time Status
                self.status = "실행 중"
                self.last_run = datetime.now()
                
                # Check for model reload (not implemented here but placeholder)
                # self.check_model_reload()
                
                current_ts = time.time()
                if current_ts < self.rest_until:
                    wait_min = (self.rest_until - current_ts) / 60
                    logger.info(f"😴 휴식 중... (남은 시간: {wait_min:.1f}분)")
                    self.status = f"Resting ({wait_min:.0f}m)"
                    for _ in range(int(wait_min * 600)): # Check every 0.1 seconds
                        if not self.is_running: break
                        time.sleep(0.1)
                    continue

                logger.debug("Fetching data...")
                df = self.fetch_data()
                if df is None:
                    self.status = "Data Fetch Error"
                    time.sleep(10)
                    continue
                
                row = df.iloc[-1]
                current_price = row['close']
                atr = row['atr']
                self.current_balance = self.balance # Sync balance for dashboard
                
                self.status = "실행 중"

                # 3. manage position
                if self.position != 0:
                    self.current_position = "LONG" if self.position > 0 else "SHORT"
                    # self.status = f"In Position: {self.current_position}"
                    self.manage_position(current_price, row['high'], row['low'], atr)
                
                # 4. entry
                elif self.position == 0:
                    self.current_position = "None"
                    self.status = "실행 중"
                    self.check_entry(df, row)
                
                # self.save_state()
                # logger.debug("Bot state saved. Waiting 60 seconds.")
                
                # Wait loop with frequent status checks (10s log)
                for i in range(600):
                    if not self.is_running: break
                    
                    if i % 100 == 0:
                        try:
                            # Lightweight status check
                            ticker = self.exchange.fetch_ticker(self.symbol)
                            current_p = ticker['last']
                            
                            p_str = "NONE"
                            if self.position > 0: p_str = f"LONG"
                            elif self.position < 0: p_str = f"SHORT"
                            
                            # Use last known indicators if available
                            rsi_str = f"{row['rsi']:.1f}" if 'row' in locals() else "-"
                            trend_val = row['ema_200'] if 'row' in locals() else 0
                            trend_str = "UP" if current_p > trend_val else "DOWN"
                            
                            msg = f"Price: {current_p:,.1f} | RSI: {rsi_str} | Trend: {trend_str} | Pos: {p_str}"
                            logger.info(msg)
                            
                        except Exception as e:
                            pass

                    time.sleep(0.1)

            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt received. Exiting bot.")
                break
            except Exception as e:
                logger.error(f"Unhandled error in main loop: {e}", exc_info=True)
                self.status = "Error"
                time.sleep(10)
        
        self.status = "Stopped" 
                

    def manage_position(self, current_price, high, low, atr):
        logger.debug(f"manage_position 호출됨. 현재 가격: {current_price}, 포지션: {self.position}")
        is_long = self.position > 0
        exit_price = None
        pnl = 0
        
        if self.use_ts:
            if is_long:
                if high > self.max_price: 
                    self.max_price = high
                    logger.debug(f"롱 포지션: 최고가 업데이트 -> {self.max_price}")
                if self.max_price > self.entry_price + (atr * self.ts_activation):
                    new_sl = self.max_price - (atr * self.ts_callback)
                    if new_sl > self.sl_price:
                        old_sl = self.sl_price
                        self.sl_price = new_sl
                        logger.info(f"📈 TS 발동: SL 상향 -> {old_sl:,.2f} -> {self.sl_price:,.2f}")
            else:
                if low < self.min_price: 
                    self.min_price = low
                    logger.debug(f"숏 포지션: 최저가 업데이트 -> {self.min_price}")
                if self.min_price < self.entry_price - (atr * self.ts_activation):
                    new_sl = self.min_price + (atr * self.ts_callback)
                    if new_sl < self.sl_price:
                        old_sl = self.sl_price
                        self.sl_price = new_sl
                        logger.info(f"📉 TS 발동: SL 하향 -> {old_sl:,.2f} -> {self.sl_price:,.2f}")

        if is_long:
            if low <= self.sl_price: 
                exit_price = self.sl_price
                logger.info(f"롱 포지션 청산 조건 충족: 현재 가격 {current_price} <= SL {self.sl_price}")
        else:
            if high >= self.sl_price: 
                exit_price = self.sl_price
                logger.info(f"숏 포지션 청산 조건 충족: 현재 가격 {current_price} >= SL {self.sl_price}")
            
        if exit_price:
            if is_long: pnl = (exit_price - self.entry_price) * self.position
            else: pnl = (self.entry_price - exit_price) * abs(self.position)
            
            self.balance += pnl
            self.trades.append({'time': datetime.now().isoformat(), 'pnl': pnl, 'type': 'LONG' if is_long else 'SHORT'})
            
            logger.info(f"💰 청산 완료! PnL: {pnl:+,.0f}원 (잔고: {self.balance:,.0f})")
            
            if pnl < 0:
                self.consecutive_losses += 1
                logger.warning(f"❌ 손실 발생. 연속 손실 횟수: {self.consecutive_losses}")
                if self.consecutive_losses >= 4:
                    self.rest_until = time.time() + (3600 * 4) 
                    logger.warning(f"⚠️ 4연패 -> 4시간 휴식 시작. 휴식 종료 시간: {datetime.fromtimestamp(self.rest_until).strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                self.consecutive_losses = 0
                logger.info(f"✅ 수익 발생. 연속 손실 횟수 초기화.")
                
            self.position = 0
            self.max_price = 0
            self.min_price = 0
            logger.debug("포지션 초기화 완료.")

    def check_entry(self, df, row):
        # logger.debug(f"check_entry 호출됨. 현재 잔고: {self.balance}, 현재 포지션: {self.position}")
        input_data = pd.DataFrame([row])
        try:
            regime = int(self.regime_model.predict(input_data[self.regime_model_data['features']])[0])
            cfg = self.regime_config.get(regime, {'action': 'skip'})
            action = cfg['action']
            regime_name = cfg['name']
            # logger.debug(f"예측된 시장 체제: {regime} ({cfg['name']}), 취할 행동: {action}")
            
            if action == 'skip':
                logger.info(f"🔍 Analysis | Regime: {regime_name} | Action: SKIP | Bal: {self.balance:.0f}")
                return
                
            signal = None
            prob = 0
            
            if action == 'long':
                prob = self.long_model.predict_proba(input_data[self.long_model_data['features']])[0][1]
                # logger.debug(f"롱 모델 예측 확률: {prob:.2%}")
                logger.info(f"🔍 Analysis | Regime: {regime_name} | Action: LONG | Prob: {prob:.2%} | Bal: {self.balance:.0f}")
                if prob > self.threshold: 
                    signal = 'long'
                    logger.info(f"✅ 롱 진입 신호 발생! (확률: {prob:.2%}, 임계값: {self.threshold:.2%})")
            elif action == 'short':
                prob = self.short_model.predict_proba(input_data[self.short_model_data['features']])[0][1]
                # logger.debug(f"숏 모델 예측 확률: {prob:.2%}")
                logger.info(f"🔍 Analysis | Regime: {regime_name} | Action: SHORT | Prob: {prob:.2%} | Bal: {self.balance:.0f}")
                if prob > self.threshold: 
                    signal = 'short'
                    logger.info(f"✅ 숏 진입 신호 발생! (확률: {prob:.2%}, 임계값: {self.threshold:.2%})")
                
            if signal:
                atr = row['atr'] if row['atr'] > 0 else row['close'] * 0.01
                risk = cfg['risk']
                leverage = cfg['leverage']
                price = row['close']
                
                risk_amt = self.balance * risk
                sl_dist = atr
                pos_value = min(risk_amt / (sl_dist/price), self.balance * leverage)
                
                quantity = pos_value / price
                self.position = quantity if signal == 'long' else -quantity
                self.entry_price = price
                
                if signal == 'long':
                    self.sl_price = price - atr
                    self.max_price = price
                    logger.info(f"🚀 롱 진입: 수량={self.position:,.4f}, 진입가={self.entry_price:,.2f}, SL={self.sl_price:,.2f}, 레버리지={leverage}x")
                else:
                    self.sl_price = price + atr
                    self.min_price = price
                    logger.info(f"🚀 숏 진입: 수량={self.position:,.4f}, 진입가={self.entry_price:,.2f}, SL={self.sl_price:,.2f}, 레버리지={leverage}x")
        except Exception as e:
            logger.error(f"예측 에러: {e}", exc_info=True)

if __name__ == "__main__":
    bot = FinalBot1H()
    bot.start()
