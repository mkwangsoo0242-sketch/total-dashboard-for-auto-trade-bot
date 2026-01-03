import ccxt
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import pandas_ta as ta
import os
import sys
import time
import logging
from dotenv import load_dotenv
from datetime import datetime
from strategy import add_indicators

# BaseBot 임포트를 위한 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bots.base_bot import BaseBot

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler()
    ]
)

class LiveTradingBot(BaseBot):
    def __init__(self):
        super().__init__(name="Bot_5M", interval="5m")
        load_dotenv()
        
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.secret = os.getenv('BINANCE_SECRET')
        self.mode = os.getenv('TRADING_MODE', 'paper').lower()
        self.symbol = os.getenv('SYMBOL', 'BTC/USDT')
        self.leverage = int(os.getenv('LEVERAGE', 10))
        self.risk_per_trade = float(os.getenv('RISK_PER_TRADE', 0.02))
        self.model_path = 'trend_xgb.pkl'
        
        # Strategy Parameters
        self.sl_atr_multiplier = 1.2
        self.tp_atr_multiplier = 3.0
        
        # Initialize Exchange
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        
        if self.mode == 'paper':
            logging.info("Paper Trading Mode Activated")
            self.exchange.set_sandbox_mode(True) # Note: CCXT sandbox might need specific URL setup for futures
            # For pure paper trading simulation without exchange connection, we might need a mock exchange.
            # But here we assume 'paper' means just logging trades or using Testnet.
            # If using Binance Testnet, ensure keys are for Testnet.
        
        # Load Model
        if os.path.exists(self.model_path):
            self.model = joblib.load(self.model_path)
            logging.info(f"ML Model loaded from {self.model_path}")
        else:
            logging.error(f"Model file {self.model_path} not found!")
            self.model = None

    def fetch_data(self, limit=200):
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe='1h', limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logging.error(f"Error fetching data: {e}")
            return None

    def prepare_features(self, df):
        try:
            df = add_indicators(df)
            
            # ML Features (Must match train_trend_model.py)
            df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
            df['dist_ema60'] = (df['close'] - df['ema_60']) / df['ema_60']
            df['rsi_change'] = df['rsi'].diff()
            df['adx_change'] = df['adx'].diff()
            df['vol_change'] = df['volume'].pct_change()
            
            df['stoch_diff'] = df['stoch_k'] - df['stoch_d']
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
            df['vol_ratio'] = df['volume'] / df['vol_ma20']
            df['ema_slope'] = df['ema_20'].pct_change() * 100
            
            return df
        except Exception as e:
            logging.error(f"Error preparing features: {e}")
            return None

    def get_signal(self, df):
        if len(df) < 60:
            return None, 0

        row = df.iloc[-1]
        
        # Base Strategy
        entry_type = None
        if row['close'] > row['ema_60'] and row['supertrend_direction'] == 1 and row['adx'] > 25:
            entry_type = 'long'
        elif row['close'] < row['ema_60'] and row['supertrend_direction'] == -1 and row['adx'] > 25:
            entry_type = 'short'
            
        if not entry_type:
            return None, 0
            
        # ML Validation
        if self.model:
            try:
                features = {
                    'rsi': row['rsi'],
                    'rsi_change': row['rsi_change'],
                    'adx': row['adx'],
                    'adx_pos': row['adx_pos'],
                    'adx_neg': row['adx_neg'],
                    'adx_change': row['adx_change'],
                    'dist_ema20': row['dist_ema20'],
                    'dist_ema60': row['dist_ema60'],
                    'atr': row['atr'],
                    'vol_change': row['vol_change'],
                    'macd_hist': row['macd_hist'],
                    'stoch_k': row['stoch_k'],
                    'stoch_d': row['stoch_d'],
                    'stoch_diff': row['stoch_diff'],
                    'bb_width': row['bb_width'],
                    'vol_ratio': row['vol_ratio'],
                    'ema_slope': row['ema_slope'],
                    'trade_type': 1 if entry_type == 'long' else 0
                }
                
                features_df = pd.DataFrame([features])
                
                # Check column order/names against model (Optional but recommended)
                # For XGBoost, feature names must match. 
                # Assuming the dict keys match the training DataFrame columns.
                
                prob = self.model.predict_proba(features_df)[0][1]
                
                if prob > 0.55: # Threshold
                    return entry_type, row['close']
                else:
                    logging.info(f"Signal filtered by ML (Prob: {prob:.4f})")
                    return None, 0
            except Exception as e:
                logging.error(f"ML Prediction Error: {e}")
                # Fallback: return signal without ML or skip? 
                # Let's skip to be safe
                return None, 0
        else:
            return entry_type, row['close']

    def calculate_position_size(self, price, atr):
        try:
            # Get Balance
            if self.mode == 'paper':
                balance = 10000 # Mock balance
            else:
                balance_info = self.exchange.fetch_balance()
                balance = balance_info['USDT']['free']
            
            sl_distance = atr * self.sl_atr_multiplier
            if sl_distance == 0:
                return 0
                
            sl_percent = sl_distance / price
            risk_amount = balance * self.risk_per_trade
            
            target_notional = risk_amount / sl_percent
            max_notional = balance * self.leverage
            
            position_size_usd = min(target_notional, max_notional)
            quantity = position_size_usd / price
            
            return quantity
        except Exception as e:
            logging.error(f"Error calculating position size: {e}")
            return 0

    def execute_trade(self, signal, price, quantity, atr):
        if quantity <= 0:
            logging.warning("Quantity is 0, skipping trade.")
            return

        logging.info(f"Executing {signal.upper()} trade. Price: {price}, Qty: {quantity:.4f}")
        
        if self.mode == 'paper':
            logging.info("[PAPER] Order Placed Successfully")
            return
            
        try:
            # Set Leverage
            try:
                self.exchange.set_leverage(self.leverage, self.symbol)
            except Exception as e:
                logging.error(f"Failed to set leverage: {e}")

            # Place Order
            side = 'buy' if signal == 'long' else 'sell'
            order = self.exchange.create_market_order(self.symbol, side, quantity)
            logging.info(f"Order Placed: {order['id']}")
            
            # Place SL/TP
            # Note: Binance Futures often requires separate calls or batch orders for SL/TP
            # This is a simplified example. In production, use 'stop_market' and 'take_profit_market'
            
            sl_price = price - (atr * self.sl_atr_multiplier) if signal == 'long' else price + (atr * self.sl_atr_multiplier)
            tp_price = price + (atr * self.tp_atr_multiplier) if signal == 'long' else price - (atr * self.tp_atr_multiplier)
            
            # Stop Loss
            sl_side = 'sell' if signal == 'long' else 'buy'
            self.exchange.create_order(
                symbol=self.symbol,
                type='STOP_MARKET',
                side=sl_side,
                amount=quantity,
                params={'stopPrice': sl_price}
            )
            logging.info(f"SL Placed at {sl_price}")
            
            # Take Profit
            self.exchange.create_order(
                symbol=self.symbol,
                type='TAKE_PROFIT_MARKET',
                side=sl_side,
                amount=quantity,
                params={'stopPrice': tp_price}
            )
            logging.info(f"TP Placed at {tp_price}")
            
        except Exception as e:
            logging.error(f"Order Execution Failed: {e}")

    def run(self):
        logging.info("Bot started...")
        while True:
            try:
                logging.info("Fetching data...")
                df = self.fetch_data()
                if df is not None:
                    df = self.prepare_features(df)
                    if df is not None:
                        signal, price = self.get_signal(df)
                        
                        if signal:
                            logging.info(f"Signal Detected: {signal} at {price}")
                            atr = df.iloc[-1]['atr']
                            qty = self.calculate_position_size(price, atr)
                            self.execute_trade(signal, price, qty, atr)
                        else:
                            logging.info("No signal.")
                        
                        # 대시보드 업데이트
                        if self.mode == 'paper':
                            balance = 10000 # Mock balance
                        else:
                            try:
                                balance_info = self.exchange.fetch_balance()
                                balance = balance_info['total']['USDT']
                            except: balance = 0
                            
                        self.current_balance = balance
                        self.status = "신호 대기 중" if not signal else f"{signal.upper()} 진입"
                        self.balance_history.append(balance)
                        if len(self.balance_history) > self.max_history:
                            self.balance_history.pop(0)
                
                # Sleep for 1 hour (or check every minute if we want to catch the exact hour close)
                # Ideally, we should sync with the candle close.
                # For simplicity, sleep 60 seconds and check if new candle arrived? 
                # Or just sleep 5 minutes.
                time.sleep(60 * 5) 
                
            except KeyboardInterrupt:
                logging.info("Bot stopped by user.")
                break
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    bot = LiveTradingBot()
    bot.run()
