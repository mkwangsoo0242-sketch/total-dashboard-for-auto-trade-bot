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
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_1h.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

load_dotenv()

class FinalBot1H:
    def __init__(self):
        self.symbol = 'BTC/USDT'
        self.timeframe = '1h'
        self.initial_balance = 100000
        self.balance = self.initial_balance
        
        self.load_models()
        
        self.api_key = os.getenv('BYBIT_API_KEY')
        self.secret = os.getenv('BYBIT_API_SECRET')
        self.exchange = ccxt.bybit({
            'apiKey': self.api_key,
            'secret': self.secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
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
        
        logging.info(f"🤖 1시간봉 최종 봇 초기화 완료")

    def start_scheduler(self):
        def job():
            logging.info("⏰ 00:00 정기 재학습 시작...")
            subprocess.Popen([sys.executable, "retrain.py"])
            
        schedule.every().day.at("00:00").do(job)
        
        def run_schedule():
            while True:
                schedule.run_pending()
                time.sleep(60)
                
        t = threading.Thread(target=run_schedule, daemon=True)
        t.start()
        logging.info("📅 자동 재학습 스케줄러 가동 (매일 00:00)")

    def check_model_reload(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, 'xgb_short_1h.pkl')
            mtime = os.path.getmtime(path)
            if mtime > self.model_ts:
                logging.info("🔄 새로운 모델 파일 감지! 다시 로드합니다.")
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
            logging.info("✅ ML 모델 로드 성공")
        except Exception as e:
            logging.error(f"❌ 모델 로드 실패: {e}")
            if not hasattr(self, 'short_model'):
                sys.exit(1)

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
            logging.error(f"데이터 조회 실패: {e}")
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
                self.balance = state.get('balance', 100000)
                self.position = state.get('position', 0)
                self.entry_price = state.get('entry_price', 0)
                self.sl_price = state.get('sl_price', 0)
                self.consecutive_losses = state.get('consecutive_losses', 0)
                self.trades = state.get('trades', [])
                if self.position > 0: self.max_price = self.entry_price
                elif self.position < 0: self.min_price = self.entry_price
            except: pass

    def run(self):
        logging.info(f"🚀 봇 시작 (잔고: {self.balance:,.0f}원)")
        
        while True:
            try:
                # 1. 휴식 체크
                current_ts = time.time()
                self.check_model_reload()
                
                if current_ts < self.rest_until:
                    wait_min = (self.rest_until - current_ts) / 60
                    logging.info(f"😴 휴식 중... (남은 시간: {wait_min:.1f}분)")
                    time.sleep(60)
                    continue

                # 2. 데이터 수집
                df = self.fetch_data()
                if df is None:
                    time.sleep(10)
                    continue
                
                row = df.iloc[-1]
                price = row['close']
                atr = row['atr']
                
                # 3. 포지션 관리
                if self.position != 0:
                    self.manage_position(price, row['high'], row['low'], atr)
                
                # 4. 신규 진입
                elif self.position == 0:
                    self.check_entry(df, row)
                
                self.save_state()
                time.sleep(60) 
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.error(f"Error: {e}")
                time.sleep(10)

    def manage_position(self, current_price, high, low, atr):
        is_long = self.position > 0
        exit_price = None
        pnl = 0
        
        if self.use_ts:
            if is_long:
                if high > self.max_price: self.max_price = high
                if self.max_price > self.entry_price + (atr * self.ts_activation):
                    new_sl = self.max_price - (atr * self.ts_callback)
                    if new_sl > self.sl_price:
                        self.sl_price = new_sl
                        logging.info(f"📈 TS 발동: SL 상향 -> {self.sl_price:,.2f}")
            else:
                if low < self.min_price: self.min_price = low
                if self.min_price < self.entry_price - (atr * self.ts_activation):
                    new_sl = self.min_price + (atr * self.ts_callback)
                    if new_sl < self.sl_price:
                        self.sl_price = new_sl
                        logging.info(f"📉 TS 발동: SL 하향 -> {self.sl_price:,.2f}")

        if is_long:
            if low <= self.sl_price: exit_price = self.sl_price
        else:
            if high >= self.sl_price: exit_price = self.sl_price
            
        if exit_price:
            if is_long: pnl = (exit_price - self.entry_price) * self.position
            else: pnl = (self.entry_price - exit_price) * abs(self.position)
            
            self.balance += pnl
            self.trades.append({'time': datetime.now().isoformat(), 'pnl': pnl, 'type': 'LONG' if is_long else 'SHORT'})
            
            logging.info(f"💰 청산 완료! PnL: {pnl:+,.0f}원")
            
            if pnl < 0:
                self.consecutive_losses += 1
                if self.consecutive_losses >= 4:
                    self.rest_until = time.time() + (3600 * 4) 
                    logging.warning(f"⚠️ 4연패 -> 4시간 휴식")
            else:
                self.consecutive_losses = 0
                
            self.position = 0
            self.max_price = 0
            self.min_price = 0

    def check_entry(self, df, row):
        input_data = pd.DataFrame([row])
        try:
            regime = int(self.regime_model.predict(input_data[self.regime_model_data['features']])[0])
            cfg = self.regime_config.get(regime, {'action': 'skip'})
            action = cfg['action']
            
            if action == 'skip':
                return
                
            signal = None
            prob = 0
            
            if action == 'long':
                prob = self.long_model.predict_proba(input_data[self.long_model_data['features']])[0][1]
                if prob > self.threshold: signal = 'long'
            elif action == 'short':
                prob = self.short_model.predict_proba(input_data[self.short_model_data['features']])[0][1]
                if prob > self.threshold: signal = 'short'
                
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
                else:
                    self.sl_price = price + atr
                    self.min_price = price
                    
                logging.info(f"🚀 진입: {signal.upper()} (확률: {prob:.1%}, 레버리지: {leverage}x)")
        except Exception as e:
            logging.error(f"예측 에러: {e}")

if __name__ == "__main__":
    bot = FinalBot1H()
    bot.run()
