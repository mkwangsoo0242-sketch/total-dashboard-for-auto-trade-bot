import pandas as pd
import joblib
import os
import logging

class Strategy:
    def __init__(self, config):
        self.config = config
        # RSI 2 parameters
        self.rsi_buy_threshold = config['strategy'].get('rsi_buy_threshold', 5)
        self.rsi_sell_threshold = config['strategy'].get('rsi_sell_threshold', 95)
        self.adx_threshold = config['strategy'].get('adx_threshold', 25)
        
        # Load LightGBM model
        self.model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lgbm_model.pkl')
        self.model = None
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
                logging.info(f"Loaded LightGBM model from {self.model_path}")
            except Exception as e:
                logging.error(f"Error loading LightGBM model: {e}")
        else:
            logging.warning("LightGBM model file not found. Model filtering will be disabled.")

        self.features = [
            'rsi_14', 'rsi_2', 'ema_20_dist', 'ema_50_dist', 'ema_200_dist', 'ema_long_dist',
            'bb_width', 'bb_pos', 'adx', 'volatility', 'volume_ratio', 'donchian_pos',
            'return_1', 'return_4', 'return_12'
        ]

    def check_entry(self, df):
        if df is None or len(df) < 2:
            return None

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Check for NaN
        if pd.isna(curr['rsi_2']) or pd.isna(curr['ema_200']):
            return None

        # --- Trend Filters ---
        ema_20 = curr.get('ema_20', 0)
        ema_50 = curr.get('ema_50', 0)
        ema_200 = curr.get('ema_200', 0)
        adx_val = curr.get('adx', 0)
        
        is_bullish_alignment = ema_20 > ema_50 > ema_200
        is_bearish_alignment = ema_20 < ema_50 < ema_200
        
        # 3. Long Term Trend (EMA 4800) - Bull Market Filter
        is_bull_market = curr['close'] > curr.get('ema_long', 0)
        
        # --- Entry Logic ---
        signal = None
        
        # 1. Dip Buy (Reversion) - Bull market pullbacks
        if is_bull_market:
            # Loosened filters for more trades in bull market
            if (curr['rsi_14'] < 45 or curr['rsi_2'] < 15) and curr['close'] > ema_200:
                if adx_val > 15 and curr.get('volatility', 0) > 0.001:
                    # Bullish candle confirmation
                    if curr['close'] > curr['open']:
                        vol_mult = self.config['strategy'].get('volume_multiplier', 0.8)
                        if curr['volume'] > curr['volume_ma'] * vol_mult:
                            signal = 'buy_dip'
                
        # 2. Breakout (Trend Following)
        if not signal:
            donchian_high_4h = curr.get('donchian_high_4h', 0)
            donchian_low_4h = curr.get('donchian_low_4h', 0)
            
            # Long Breakout: Strong momentum
            if curr['close'] > donchian_high_4h and prev['close'] <= donchian_high_4h:
                # Stricter ADX for non-bull markets to avoid false breakouts
                breakout_adx = 25 if not is_bull_market else 20
                if adx_val > breakout_adx and curr['volume'] > curr['volume_ma'] * 1.1:
                    if curr['rsi_14'] < 85: # Slightly loosened RSI cap
                        signal = 'buy_breakout'
            
            # Short Breakout: Strong momentum
            elif curr['close'] < donchian_low_4h and prev['close'] >= donchian_low_4h:
                if adx_val > 25 and curr['volume'] > curr['volume_ma'] * 1.1:
                    if curr['rsi_14'] > 15: # Slightly loosened RSI cap
                        signal = 'sell_breakout'
  
        # 3. Short Signal (Bear Market Reversion)
        if not signal and not is_bull_market:
            # Loosened filters for more trades in bear market (Sell the Rip)
            if (curr['rsi_14'] > 50 or curr['rsi_2'] > 80) and curr['close'] < ema_200:
                if adx_val < 45 and curr.get('volatility', 0) > 0.0008:
                    # Bearish candle confirmation
                    if curr['close'] < curr['open'] or curr['close'] < prev['close']:
                        vol_mult = self.config['strategy'].get('volume_multiplier', 0.7)
                        if curr['volume'] > curr['volume_ma'] * vol_mult:
                            signal = 'sell'

        if not signal:
            return None

        # --- LightGBM Confidence Filter ---
        lgbm_confirm = True
        if signal and self.model is not None:
            try:
                # Prepare features for prediction
                feat_values = [curr.get(f, 0) for f in self.features]
                feat_df = pd.DataFrame([feat_values], columns=self.features)
                
                # Predict probability
                prob = self.model.predict_proba(feat_df)[0][1] # Probability of class 1 (price up)
                
                # Threshold from config or default
                base_threshold = self.config['strategy'].get('lgbm_threshold', 0.55)
                
                # Signal-specific threshold adjustments
                if signal == 'buy_breakout' or signal == 'sell_breakout':
                    threshold = base_threshold - 0.05 # Be more lenient with breakouts
                elif signal == 'buy_dip':
                    threshold = base_threshold
                elif signal == 'sell':
                    threshold = base_threshold + 0.05 # Be very strict with sells
                else:
                    threshold = base_threshold
                
                if 'buy' in signal:
                    lgbm_confirm = prob >= threshold
                    if not lgbm_confirm:
                        logging.debug(f"Signal {signal} rejected by LGBM: prob {prob:.4f} < {threshold}")
                elif 'sell' in signal:
                    lgbm_confirm = prob <= (1 - threshold)
                    if not lgbm_confirm:
                        logging.debug(f"Signal {signal} rejected by LGBM: prob {prob:.4f} > {1-threshold}")
                    
            except Exception as e:
                logging.error(f"Error during LightGBM prediction: {e}")
                lgbm_confirm = True # Fallback to true if error
        
        return signal if lgbm_confirm else None

    def calculate_stops(self, df, side, entry_price):
        curr = df.iloc[-1]
        atr = curr['atr']
        if pd.isna(atr): atr = entry_price * 0.01
        
        # Dynamic multipliers based on signal type
        if side == 'buy_dip':
            sl_mult = self.config['strategy'].get('atr_sl_dip', 3.0)
            tp_mult = self.config['strategy'].get('atr_tp_dip', 15.0)
        elif side == 'buy_breakout':
            sl_mult = self.config['strategy'].get('atr_sl_breakout', 3.0)
            tp_mult = self.config['strategy'].get('atr_tp_breakout', 35.0)
        elif side == 'sell_breakout':
            sl_mult = self.config['strategy'].get('atr_sl_breakout', 3.0)
            tp_mult = self.config['strategy'].get('atr_tp_breakout', 35.0)
        elif side == 'sell':
            sl_mult = self.config['strategy'].get('atr_sl_sell', 3.0)
            tp_mult = self.config['strategy'].get('atr_tp_sell', 12.0)
        else:
            sl_mult = self.config['strategy'].get('stop_loss_atr_mult', 3.0)
            tp_mult = self.config['strategy'].get('take_profit_atr_mult', 12.0)
        
        if 'buy' in side:
            sl = entry_price - (atr * sl_mult)
            tp = entry_price + (atr * tp_mult)
        else:
            sl = entry_price + (atr * sl_mult)
            tp = entry_price - (atr * tp_mult)
            
        return sl, tp

    def check_exit(self, df, position):
        if df is None or position is None:
            return None
            
        curr = df.iloc[-1]
        side = position['side']
        entry_price = position['entry']
        current_sl = position.get('stop_loss', 0)
        
        if pd.isna(curr['sma_5']): return None

        # 1. Breakeven Logic (From Optimized Strategy)
        if self.config['strategy'].get('use_breakeven', False):
            be_mult = self.config['strategy'].get('breakeven_activation_atr', 4.0)
            atr = curr['atr']
            if side in ['buy', 'buy_dip', 'buy_breakout']:
                if (curr['high'] - entry_price) > (atr * be_mult):
                    new_sl = entry_price + (entry_price * 0.0001) # Entry + small slippage
                    if new_sl > current_sl:
                        return {'action': 'update_sl', 'price': new_sl, 'reason': 'breakeven'}
            elif side in ['sell', 'sell_breakout']:
                if (entry_price - curr['low']) > (atr * be_mult):
                    new_sl = entry_price - (entry_price * 0.0001)
                    if new_sl < current_sl or current_sl == 0:
                        return {'action': 'update_sl', 'price': new_sl, 'reason': 'breakeven'}

        # 2. Dynamic Trailing Stop (From Optimized Strategy)
        if self.config['strategy'].get('use_trailing_stop', False):
            activation_mult = self.config['strategy'].get('trailing_stop_activation_atr', 6.0)
            sl_mult = self.config['strategy'].get('stop_loss_atr_mult', 3.0)
            atr = curr['atr']
            
            if side in ['buy', 'buy_dip', 'buy_breakout']:
                if (curr['high'] - entry_price) > (atr * activation_mult):
                    new_sl = curr['high'] - (atr * sl_mult)
                    if new_sl > current_sl:
                        return {'action': 'update_sl', 'price': new_sl, 'reason': 'trailing_stop'}
            elif side in ['sell', 'sell_breakout']:
                if (entry_price - curr['low']) > (atr * activation_mult):
                    new_sl = curr['low'] + (atr * sl_mult)
                    if new_sl < current_sl or current_sl == 0:
                        return {'action': 'update_sl', 'price': new_sl, 'reason': 'trailing_stop'}

        # 3. RSI Overbought/Oversold Exit (Only for Mean Reversion trades)
        if side in ['buy', 'buy_dip']:
            if curr['rsi_14'] > 80:
                return {'action': 'close', 'reason': 'rsi_overbought'}
        elif side == 'sell':
            if curr['rsi_14'] < 20:
                return {'action': 'close', 'reason': 'rsi_oversold'}

        # 4. Mean Reversion Exit (BB Touch or SMA 20)
        # Only for mean reversion signals
        if side in ['buy', 'buy_dip', 'sell']:
            if side in ['buy', 'buy_dip']:
                # Exit if Close > BB Upper or RSI > 70
                if ('bb_upper' in curr and curr['close'] > curr['bb_upper']) or curr['rsi_14'] > 70:
                    return {'action': 'close', 'reason': 'mean_reversion_exit'}
            elif side == 'sell':
                # Exit if Close < BB Lower or RSI < 30
                if ('bb_lower' in curr and curr['close'] < curr['bb_lower']) or curr['rsi_14'] < 30:
                    return {'action': 'close', 'reason': 'mean_reversion_exit'}
                    
        return None
