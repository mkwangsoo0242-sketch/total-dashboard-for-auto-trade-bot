import pandas as pd
import numpy as np
import joblib
import os
from datetime import datetime
from strategy import add_indicators

class Backtester:
    def __init__(self, data_path, model_path='trend_xgb.pkl'):
        self.data_path = data_path
        self.model_path = model_path
        self.model = None
        self.df = None
        
        self.load_data()
        self.load_model()
        
        # Strategy Parameters (matching live_trading_bot)
        self.sl_atr_multiplier = 1.2
        self.tp_atr_multiplier = 3.0
        self.risk_per_trade = 0.02 # 2% risk
        self.initial_balance = 10000 # USD
        self.leverage = 10
        
        # Backtesting state
        self.balance = self.initial_balance
        self.position = 0 # 0: no position, >0: long, <0: short
        self.entry_price = 0
        self.entry_time = None
        self.trades = []
        self.current_atr = 0
        
    def load_data(self):
        print(f"Loading data from {self.data_path}")
        df = pd.read_csv(self.data_path)
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
        
        # Resample to 1H
        print("Resampling to 1H...")
        df_1h = df.resample('1h').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        df_1h.dropna(inplace=True)
        self.df = df_1h.reset_index()
        print(f"Data loaded and resampled. Total 1H candles: {len(self.df)}")
        
    def load_model(self):
        if os.path.exists(self.model_path):
            self.model = joblib.load(self.model_path)
            print(f"ML Model loaded from {self.model_path}")
        else:
            print(f"Model file {self.model_path} not found! Backtesting without ML validation.")
            self.model = None
            
    def prepare_features(self, df_slice):
        # Ensure add_indicators is applied to a copy to avoid SettingWithCopyWarning
        processed_df = add_indicators(df_slice.copy())
        
        # ML Features (Must match train_trend_model.py)
        processed_df['dist_ema20'] = (processed_df['close'] - processed_df['ema_20']) / processed_df['ema_20']
        processed_df['dist_ema60'] = (processed_df['close'] - processed_df['ema_60']) / processed_df['ema_60']
        processed_df['rsi_change'] = processed_df['rsi'].diff()
        processed_df['adx_change'] = processed_df['adx'].diff()
        processed_df['vol_change'] = processed_df['volume'].pct_change()
        
        processed_df['stoch_diff'] = processed_df['stoch_k'] - processed_df['stoch_d']
        processed_df['bb_width'] = (processed_df['bb_upper'] - processed_df['bb_lower']) / processed_df['bb_middle']
        processed_df['vol_ratio'] = processed_df['volume'] / processed_df['vol_ma20']
        processed_df['ema_slope'] = processed_df['ema_20'].pct_change() * 100
        
        return processed_df

    def get_signal(self, row):
        # Base Strategy (matching train_trend_model.py and live_trading_bot.py)
        entry_type = None
        if row['close'] > row['ema_60'] and row['supertrend_direction'] == 1 and row['adx'] > 25:
            entry_type = 'long'
        elif row['close'] < row['ema_60'] and row['supertrend_direction'] == -1 and row['adx'] > 25:
            entry_type = 'short'
            
        if not entry_type:
            return None
            
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
                prob = self.model.predict_proba(features_df)[0][1]
                
                if prob > 0.55: # Threshold
                    return entry_type
                else:
                    # print(f"Signal filtered by ML (Prob: {prob:.4f})")
                    return None
            except Exception as e:
                print(f"ML Prediction Error: {e}")
                return None
        else:
            return entry_type

    def calculate_position_size(self, price, atr):
        if atr == 0:
            return 0
            
        sl_distance = atr * self.sl_atr_multiplier
        if sl_distance == 0:
            return 0
            
        sl_percent = sl_distance / price
        risk_amount = self.balance * self.risk_per_trade
        
        target_notional = risk_amount / sl_percent
        max_notional = self.balance * self.leverage
        
        position_size_usd = min(target_notional, max_notional)
        quantity = position_size_usd / price
        
        return quantity

    def execute_trade(self, signal, price, quantity, current_candle_time):
        if quantity <= 0:
            return
            
        trade_info = {
            'entry_time': current_candle_time,
            'entry_price': price,
            'signal': signal,
            'quantity': quantity,
            'balance_before': self.balance
        }
        
        self.entry_price = price
        self.position = quantity if signal == 'long' else -quantity
        self.entry_time = current_candle_time
        
        # Calculate SL/TP for this trade
        sl_price = price - (self.current_atr * self.sl_atr_multiplier) if signal == 'long' else price + (self.current_atr * self.sl_atr_multiplier)
        tp_price = price + (self.current_atr * self.tp_atr_multiplier) if signal == 'long' else price - (self.current_atr * self.tp_atr_multiplier)
        
        trade_info['sl_price'] = sl_price
        trade_info['tp_price'] = tp_price
        
        self.trades.append(trade_info)
        print(f"[{current_candle_time}] ENTER {signal.upper()} at {price:.2f} with {quantity:.4f} BTC. SL: {sl_price:.2f}, TP: {tp_price:.2f}")

    def close_trade(self, exit_price, current_candle_time, exit_reason="Signal"): # Added exit_reason
        if self.position == 0:
            return
            
        trade = self.trades[-1] # Get the last open trade
        
        pnl = (exit_price - self.entry_price) * self.position
        self.balance += pnl
        
        trade['exit_time'] = current_candle_time
        trade['exit_price'] = exit_price
        trade['pnl'] = pnl
        trade['balance_after'] = self.balance
        trade['exit_reason'] = exit_reason # Store exit reason
        
        print(f"[{current_candle_time}] EXIT {trade['signal'].upper()} at {exit_price:.2f}. PnL: {pnl:.2f}. New Balance: {self.balance:.2f} ({exit_reason})")
        
        self.position = 0
        self.entry_price = 0
        self.entry_time = None
        self.current_atr = 0

    def run_backtest(self):
        if self.df is None or self.df.empty:
            print("No data to backtest.")
            return
            
        # Need enough data for indicators (e.g., EMA60, ADX14, Supertrend)
        # Let's assume 100 candles are enough for initial warm-up
        warmup_period = 100 
        
        print(f"Starting backtest with initial balance: {self.initial_balance}")
        
        for i in range(warmup_period, len(self.df)):
            current_candle = self.df.iloc[i]
            current_candle_time = current_candle['datetime']
            
            # Prepare features for the current and past candles needed for indicators
            df_slice = self.df.iloc[max(0, i-warmup_period-60):i+1] # Ensure enough history for indicators
            processed_df_slice = self.prepare_features(df_slice)
            
            if processed_df_slice.empty:
                continue
                
            current_processed_row = processed_df_slice.iloc[-1]
            
            # Update current ATR for SL/TP calculation
            self.current_atr = current_processed_row['atr']
            
            # Check for open position exit conditions
            if self.position != 0:
                trade = self.trades[-1]
                
                # Check Stop Loss
                if trade['signal'] == 'long' and current_candle['low'] <= trade['sl_price']:
                    self.close_trade(trade['sl_price'], current_candle_time, "SL Hit")
                    
                elif trade['signal'] == 'short' and current_candle['high'] >= trade['sl_price']:
                    self.close_trade(trade['sl_price'], current_candle_time, "SL Hit")
                    
                # Check Take Profit
                elif trade['signal'] == 'long' and current_candle['high'] >= trade['tp_price']:
                    self.close_trade(trade['tp_price'], current_candle_time, "TP Hit")
                    
                elif trade['signal'] == 'short' and current_candle['low'] <= trade['tp_price']:
                    self.close_trade(trade['tp_price'], current_candle_time, "TP Hit")
                    
            # If no position, check for entry signal
            if self.position == 0:
                signal = self.get_signal(current_processed_row)
                if signal:
                    quantity = self.calculate_position_size(current_processed_row['close'], current_processed_row['atr'])
                    self.execute_trade(signal, current_processed_row['close'], quantity, current_candle_time)
                    
        print("\nBacktest Finished.")
        print(f"Final Balance: {self.balance:.2f}")
        print(f"Total Trades: {len(self.trades)}")
        
        # Analyze trades
        winning_trades = [t for t in self.trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in self.trades if t.get('pnl', 0) <= 0]
        
        win_rate = len(winning_trades) / len(self.trades) if len(self.trades) > 0 else 0
        total_pnl = sum(t.get('pnl', 0) for t in self.trades)
        
        print(f"Winning Trades: {len(winning_trades)}")
        print(f"Losing Trades: {len(losing_trades)}")
        print(f"Win Rate: {win_rate:.2%}")
        print(f"Total PnL: {total_pnl:.2f}")
        print(f"Initial Balance: {self.initial_balance:.2f}")
        print(f"Final Balance: {self.balance:.2f}")
        
        # Optional: More detailed metrics like Sharpe Ratio, Max Drawdown, etc.
        # For simplicity, we'll stick to basic metrics for now.

if __name__ == "__main__":
    backtester = Backtester('data/btc_usdt_5m_3y.csv')
    backtester.run_backtest()
