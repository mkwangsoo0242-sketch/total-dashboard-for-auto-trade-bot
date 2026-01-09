import schedule
import random
import subprocess
import threading
import os
import sys
import time
import ccxt
import joblib
import pandas as pd
import logging
from datetime import datetime
from dotenv import load_dotenv

# .env 파일 로드
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path)

from strategy_5m import add_indicators

# Define Regime Settings (Default)
REGIME_SETTINGS = {
    0: {'name': 'SIDEWAYS', 'skip': True},
    1: {'name': 'BULLISH', 'direction': 'long', 'threshold': 0.6, 'risk': 0.1, 'leverage': 5, 'sl_mult': 2.0},
    2: {'name': 'BEARISH', 'direction': 'short', 'threshold': 0.6, 'risk': 0.1, 'leverage': 5, 'sl_mult': 2.0}
}

# 로그 설정 (전용 핸들러 사용으로 격리)
log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, 'bot.log')

logger = logging.getLogger("BTC_5M_Bot")
logger.setLevel(logging.INFO)
if not logger.handlers:
    # 파일 핸들러
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)
    # 콘솔 핸들러
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(sh)
    # 다른 로거로 전파되지 않도록 설정
    logger.propagate = False

class LiveTradingBot:
    def execute_logic(self):
        # BaseBot compatibility
        pass

    def stop(self):
        self.is_running = False
        self.status = "Stopped"
        logger.info("Stopping 5M Bot...")

    def __init__(self):
        # 5분봉 전용 키 우선 적용
        self.api_key = os.getenv('BYBIT_API_KEY_5M') or os.getenv('BYBIT_API_KEY') or os.getenv('BINANCE_API_KEY')
        self.secret = os.getenv('BYBIT_SECRET_5M') or os.getenv('BYBIT_SECRET') or os.getenv('BINANCE_SECRET')
        self.mode = os.getenv('TRADING_MODE', 'paper').lower()
        self.symbol = os.getenv('SYMBOL', 'BTC/USDT')
        self.timeframe = '5m'
        
        # 가상 거래 상태 변수
        self.paper_balance = 100.0
        self.paper_position = None # {'amount': 0.0, 'entry': 0.0, 'type': 'long'/'short'}

        # Manager Compatibility Attributes
        self.interval = '5m'
        self.current_balance = self.paper_balance if self.mode == 'paper' else 0.0
        self.status = "신호 대기 중 (초기화)"
        self.balance_history = []
        self.current_position = None
        self.entry_price = 0 # New attribute for dashboard
        self.sl_price = 0 # New attribute for dashboard
        self.liquidation_price = 0
        self.liquidation_profit = 0
        self.total_roi = 0
        self.max_history = 50

        # 모델 로드
        self.model_ts = 0
        self.load_models()
        self.start_scheduler()
        
        # 거래소 초기화
        exchange_config = {
            'apiKey': self.api_key,
            'secret': self.secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        }
        if self.mode == 'paper':
            exchange_config['apiKey'] = None
            exchange_config['secret'] = None
            class MockExchange:
                def __init__(self):
                    self.balance = {'USDT': {'free': 100.0, 'total': 100.0}}
                    self.ticker_price = 90000.0 # Default mock price
                    self.ohlcv_data = [] # To store mock OHLCV
                    self.positions = [] # To store mock positions

                def fetch_ticker(self, symbol):
                    return {'last': self.ticker_price}

                def fetch_balance(self):
                    return self.balance

                def fetch_ohlcv(self, symbol, timeframe, limit):
                    # Fetch REAL OHLCV data even in paper mode
                    try:
                        # Create a temporary public instance for fetching data
                        public_exchange = ccxt.bybit()
                        ohlcv = public_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                        self.ohlcv_data = ohlcv
                        self.ticker_price = ohlcv[-1][4] # Sync ticker with last close
                    except Exception as e:
                        print(f"Error fetching real OHLCV: {e}")
                        # Fallback to single dummy point if failed
                        if not self.ohlcv_data:
                            now = int(time.time() * 1000)
                            self.ohlcv_data = [[now, 90000, 90000, 90000, 90000, 100]]

                    return self.ohlcv_data[-limit:]

                def create_market_order(self, symbol, side, amount):
                    self.ticker_price = self.fetch_ticker(symbol)['last'] # Update price for order
                    if side == 'buy':
                        self.balance['USDT']['free'] -= amount * self.ticker_price
                        self.balance['USDT']['total'] -= amount * self.ticker_price
                        # Simple position tracking
                        self.positions.append({'symbol': symbol.replace('/', ''), 'positionAmt': amount, 'entryPrice': self.ticker_price})
                    elif side == 'sell':
                        self.balance['USDT']['free'] += amount * self.ticker_price
                        self.balance['USDT']['total'] += amount * self.ticker_price
                        # Simple position tracking
                        self.positions = [p for p in self.positions if p['symbol'] != symbol.replace('/', '')] # Remove position
                    return {'info': 'mock_order_id'}

                def set_leverage(self, leverage, symbol):
                    pass # No actual leverage in mock

            self.exchange = MockExchange()
        else:
            self.exchange = ccxt.bybit(exchange_config)
        
        # ... (기존 모드 체크)
        
        logger.info(f"봇 초기화 완료: {self.symbol} ({self.timeframe})")

    # ... (start_scheduler, check_model_reload, load_models, fetch_data, get_features, predict_regime, predict_probs omitted - keep existing)

    def get_position(self):
        """현재 포지션 조회"""
        if self.mode == 'paper':
            if self.exchange.positions:
                pos = self.exchange.positions[0] # Assuming only one position for simplicity
                return {'amount': pos['positionAmt'], 'entry': pos['entryPrice'], 'type': 'long' if pos['positionAmt'] > 0 else 'short'}
            return None

        try:
            balance = self.exchange.fetch_balance()
            if 'info' not in balance or 'positions' not in balance['info']:
                logger.warning("Balance info or positions not found in exchange response.")
                return None
            positions = balance['info']['positions']
            for pos in positions:
                if pos['symbol'] == self.symbol.replace('/', ''):
                    amt = float(pos['positionAmt'])
                    if amt != 0:
                        return {'amount': amt, 'entry': float(pos['entryPrice']), 'type': 'long' if amt > 0 else 'short'}
            return None
        except Exception as e:
            logger.error(f"포지션 조회 실패: {e}")
            return None

    def execute_trade(self, signal, amount, leverage):
        """주문 실행"""
        if self.mode == 'paper':
            # Use MockExchange's create_market_order for simulation
            self.exchange.create_market_order(self.symbol, 'buy' if signal == 'long' else 'sell', amount)
            self.current_balance = self.exchange.fetch_balance()['USDT']['free']
            logger.info(f"🧪 [PAPER] 체결: {signal.upper()} {amount} @ {self.exchange.fetch_ticker(self.symbol)['last']} | 잔고: {self.current_balance:.2f}")
            return True
        
        try:
            # 레버리지 설정
            self.exchange.set_leverage(leverage, self.symbol)
            
            side = 'buy' if signal == 'long' else 'sell'
            order = self.exchange.create_market_order(self.symbol, side, amount)
            logger.info(f"✅ 주문 체결: {side} {amount} {self.symbol}")
            return order
        except Exception as e:
            logger.error(f"주문 실패: {e}")
            return None

    def close_position(self):
        """포지션 종료"""
        pos = self.get_position()
        if pos:
            amount = abs(pos['amount'])
            
            # Paper Mode Simulation
            if self.mode == 'paper':
                # For paper mode, simply clear the position
                self.paper_position = None
                logger.info(f"🧪 [PAPER] 포지션 종료 시뮬레이션 완료.")
                return

            side = 'sell' if pos['type'] == 'long' else 'buy'
            try:
                self.exchange.create_market_order(self.symbol, side, amount)
                logger.info("✅ 포지션 종료 완료")
            except Exception as e:
                logger.error(f"포지션 종료 실패: {e}")

    def start_scheduler(self):
        def job():
            logger.info("⏰ 00:00 정기 재학습 시작...")
            subprocess.Popen([sys.executable, "retrain.py"])
            
        schedule.every().day.at("00:00").do(job)
        
        def run_schedule():
            while True:
                schedule.run_pending()
                time.sleep(60)
                
        try:
            t = threading.Thread(target=run_schedule, daemon=True)
            t.start()
            logger.info("📅 자동 재학습 스케줄러 가동 (매일 00:00)")
        except Exception as e:
            logger.error(f"스케줄러 시작 실패: {e}")

    def check_model_reload(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, 'short_model.pkl')
            if os.path.exists(path):
                mtime = os.path.getmtime(path)
                if mtime > self.model_ts:
                    logger.info("🔄 새로운 모델 파일 감지! 다시 로드합니다.")
                    self.load_models()
        except: pass

    def load_models(self):
        """다중 모델 로드"""
        try:
            logger.info("🤖 ML 모델 로딩...")
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
            path = os.path.join(base_dir, 'short_model.pkl')
            if os.path.exists(path):
                self.model_ts = os.path.getmtime(path)
                
            self.short_model_data = joblib.load(os.path.join(base_dir, 'short_model.pkl'))
            self.long_model_data = joblib.load(os.path.join(base_dir, 'long_model.pkl'))
            self.regime_model_data = joblib.load(os.path.join(base_dir, 'regime_model.pkl'))
            
            self.short_model = self.short_model_data['model']
            self.long_model = self.long_model_data['model']
            self.regime_model = self.regime_model_data['model']
            
            logger.info(f"   Short 모델 정확도: {self.short_model_data.get('accuracy', 0)*100:.1f}%")
            logger.info(f"   Long 모델 정확도: {self.long_model_data.get('accuracy', 0)*100:.1f}%")
            logger.info(f"   Regime 모델 정확도: {self.regime_model_data.get('accuracy', 0)*100:.1f}%")
        except Exception as e:
            logger.error(f"모델 로드 실패: {e}")
            if not hasattr(self, 'short_model'):
                sys.exit(1)

    def fetch_data(self, limit=250):
        """데이터 수집 및 전처리"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=limit)
            
            # 차트용 데이터 저장 (최근 100개만)
            self.recent_candles = [
                {'x': item[0], 'y': [item[1], item[2], item[3], item[4]]}
                for item in ohlcv[-100:]
            ]

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # 지표 추가 (strategy.py 사용)
            df = add_indicators(df)
            
            # 추가 피처 (훈련 시와 동일하게)
            df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
            df['dist_ema60'] = (df['close'] - df['ema_60']) / df['ema_60']
            df['rsi_change'] = df['rsi'].diff()
            df['adx_change'] = df['adx'].diff()
            df['vol_change'] = df['volume'].pct_change()
            df['stoch_diff'] = df['stoch_k'] - df['stoch_d']
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
            df['vol_ratio'] = df['volume'] / df['vol_ma20']
            df['ema_slope'] = df['ema_20'].pct_change() * 100
            df['ema_200'] = df['close'].ewm(span=200).mean()
            df['dist_ema200'] = (df['close'] - df['ema_200']) / df['ema_200']
            
            return df
        except Exception as e:
            logger.error(f"데이터 수집 중 오류: {e}")
            return None

    def get_features(self, row, feature_list):
        """모델 입력 피처 추출"""
        features = {}
        for f in feature_list:
            val = row.get(f, 0)
            features[f] = val if not pd.isna(val) else 0
        return pd.DataFrame([features])

    def predict_regime(self, row):
        """시장 레짐 예측"""
        try:
            features = self.get_features(row, self.regime_model_data['features'])
            return int(self.regime_model.predict(features)[0])
        except:
            return 0 # 기본값 SIDEWAYS

    def predict_probs(self, row):
        """Long/Short 확률 예측"""
        try:
            l_feat = self.get_features(row, self.long_model_data['features'])
            s_feat = self.get_features(row, self.short_model_data['features'])
            
            l_prob = self.long_model.predict_proba(l_feat)[0][1]
            s_prob = self.short_model.predict_proba(s_feat)[0][1]
            
            return l_prob, s_prob
        except:
            return 0.5, 0.5

    def get_position(self):
        """현재 포지션 조회"""
        try:
            if self.mode == 'paper':
                return self.paper_position

            balance = self.exchange.fetch_balance()
            if 'info' not in balance or 'positions' not in balance['info']:
                logger.warning("Balance info or positions not found in exchange response.")
                return None
            positions = balance['info']['positions']
            for pos in positions:
                if pos['symbol'] == self.symbol.replace('/', ''):
                    amt = float(pos['positionAmt'])
                    if amt != 0:
                        return {'amount': amt, 'entry': float(pos['entryPrice']), 'type': 'long' if amt > 0 else 'short'}
            return None
        except Exception as e:
            logger.error(f"포지션 조회 실패: {e}")
            return None

    def execute_trade(self, signal, amount, leverage, sl_price=0, liq_price=0):
        """주문 실행"""
        if self.mode == 'paper':
            logger.info(f"🧪 [PAPER] {signal} 주문 시뮬레이션: 수량 {amount}, 레버리지 {leverage}")
            
            # Update Paper Position
            current_price = self.recent_candles[-1]['y'][3] if self.recent_candles else 90000
            
            self.paper_position = {
                'type': signal,
                'entry': current_price,
                'amount': amount,
                'leverage': leverage,
                'sl': sl_price
            }
            self.entry_price = current_price # FOR DASHBOARD
            self.sl_price = sl_price
            self.liquidation_price = liq_price
            self.current_position = signal.upper()
            self.status = f"포지션 보유 중 ({signal.upper()})"
            return True
        
        try:
            # 레버리지 설정
            self.exchange.set_leverage(leverage, self.symbol)
            
            side = 'buy' if signal == 'long' else 'sell'
            order = self.exchange.create_market_order(self.symbol, side, amount)
            logger.info(f"✅ 주문 체결: {side} {amount} {self.symbol}")
            return order
        except Exception as e:
            logger.error(f"주문 실패: {e}")
            return None

    def close_position(self):
        """포지션 종료"""
        pos = self.get_position()
        if pos:
            amount = abs(pos['amount'])
            side = 'sell' if pos['type'] == 'long' else 'buy'
            if self.mode == 'paper':
                current_price = self.recent_candles[-1]['y'][3] if self.recent_candles else 90000
                # 페이퍼 포지션 종료 시뮬레이션
                if pos['type'] == 'long':
                    profit = (current_price - pos['entry']) * amount
                else: # short
                    profit = (pos['entry'] - current_price) * amount
                self.paper_balance += profit # 간단한 수익/손실 반영
                self.paper_position = None
                self.current_balance = self.paper_balance
                self.current_position = None
                self.entry_price = 0
                self.sl_price = 0
                self.liquidation_price = 0
                self.liquidation_profit = 0
                logger.info(f"🧪 [PAPER] 포지션 종료 시뮬레이션: {side} {amount} | 잔고: {self.current_balance:.2f}")
            else:
                try:
                    self.exchange.create_market_order(self.symbol, side, amount)
                    logger.info("✅ 포지션 종료 완료")
                except Exception as e:
                    logger.error(f"포지션 종료 실패: {e}")

    def wait_while_running(self, seconds):
        # 0.1초씩 여러 번 대기하여 봇 중지 명령에 더 빠르게 반응
        time.sleep(seconds)

    def run(self):
        logger.info("🚀 라이브 트레이딩 봇 시작 (다중 ML 모델)")
        self.status = "신호 대기 중 (시작)"
        self.is_running = True
        
        while self.is_running:
            try:
                from datetime import datetime
                self.last_run = datetime.now()
                
                self.last_run = datetime.now()
                
                self.status = "실행 중"
                # 1. 데이터 수집
                df = self.fetch_data()
                if df is None:
                    self.status = "오류 (데이터 수집 실패)"
                    self.wait_while_running(60)
                    continue
                
                current = df.iloc[-1]
                price = current['close']
                
                # 2. 포지션 확인
                position = self.get_position()
                
                # 차트용 데이터 저장 (최근 100개)
                self.recent_candles = [
                    {'x': int(row.name.timestamp() * 1000) if hasattr(row.name, 'timestamp') else int(row.name), 
                     'y': [row['open'], row['high'], row['low'], row['close']]}
                    for idx, row in df.tail(100).iterrows()
                ]

                # 3. 신호 생성
                regime = self.predict_regime(current)
                settings = REGIME_SETTINGS.get(regime, {'skip': True})
                
                settings_name = settings.get('name', 'UNKNOWN')
                logger.info(f"📊 현재 시장 레짐: {settings_name} (가격: {price:,.2f})")
                
                # Update Status for Manager
                if position:
                     self.status = f"{position.get('type','').upper()} 보유 중 (진입가: {position.get('entry', 0):,.0f})"
                else:
                     self.status = "실행 중"
                
                if position:
                    logger.info(f"🔥 포지션 보유 중: {position['type']} {position['amount']}")
                    # 여기서 청산 로직 추가 가능 (SL/TP 등)
                    # 현재는 전략에 맡김
                
                elif not settings.get('skip'):
                    l_prob, s_prob = self.predict_probs(current)
                    direction = settings['direction']
                    threshold = settings['threshold']
                    
                    signal = None
                    if direction == 'long' and l_prob > threshold:
                        signal = 'long'
                        logger.info(f"🔍 Long 신호 감지! (확률: {l_prob:.2%})")
                    elif direction == 'short' and s_prob > threshold:
                        signal = 'short'
                        logger.info(f"🔍 Short 신호 감지! (확률: {s_prob:.2%})")
                    
                    if signal:
                        # 자금 관리
                        balance = self.exchange.fetch_balance()['USDT']['free']
                        risk = settings['risk']
                        leverage = settings['leverage']
                        
                        # ATR 기반 포지션 사이징
                        atr = current['atr'] if not pd.isna(current['atr']) else price * 0.01
                        sl_pct = (atr * settings['sl_mult']) / price
                        
                        risk_amt = balance * risk
                        target_size = risk_amt / sl_pct
                        max_size = balance * leverage
                        
                        final_size_usd = min(target_size, max_size)
                        amount = final_size_usd / price
                        
                        # Calculate Prices
                        sl_price_val = price * (1 - sl_pct) if signal == 'long' else price * (1 + sl_pct)
                        liq_price_val = price * (1 - 1/leverage) if signal == 'long' else price * (1 + 1/leverage)
                        
                        logger.info(f"🚀 진입 결정: {signal} | 크기: ${final_size_usd:.2f} ({amount:.4f} BTC)")
                        self.execute_trade(signal, amount, leverage, sl_price=sl_price_val, liq_price=liq_price_val)
                else:
                    logger.info("⏸️ 횡보장 또는 스킵 구간 - 관망")
                
                logger.info("💤 다음 캔들 대기 (5분)...")
                
                # 모델 업데이트 체크
                self.check_model_reload()
                
                self.wait_while_running(300)  # 5분 대기
                
            except KeyboardInterrupt:
                logger.info("⏹️ 봇 중지")
                break
            except Exception as e:
                logger.error(f"예기치 않은 오류: {e}")
                self.status = f"오류 ({str(e)[:20]}...)"
                self.wait_while_running(60)
        
        self.status = "Stopped"
        logger.info("5M Bot Stopped Loop.")

if __name__ == "__main__":
    bot = LiveTradingBot()
    bot.run()
