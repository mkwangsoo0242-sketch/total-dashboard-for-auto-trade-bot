import pandas as pd
import pandas_ta as ta
import numpy as np
import os

class Strategy30m:
    """
    Unified 30m Strategy Class
    - Modular 'Box' design: Can switch between different logic engines.
    - Default 'RobustExtreme' logic: Proven performance in 2023, 2024, and 2025.
    """
    def __init__(self, initial_leverage=5, mode='robust_extreme'):
        self.base_leverage = initial_leverage
        self.mode = mode # 'robust_extreme', 'robust_dual', 'robust_adaptive', 'extreme_growth'
        
        # --- Base Parameters ---
        self.base_ratio = 0.5         # Default increased for growth
        self.leverage = initial_leverage
        
        # --- Donchian Windows (Trend) ---
        self.entry_window = 48        # 1 day (standard)
        self.exit_window = 24         # 12 hours (standard)
        
        # --- Extreme Growth Parameters ---
        if mode == 'extreme_growth':
            self.entry_window = 48    # 24 hours
            self.exit_window = 24     # 12 hours
            self.base_ratio = 0.2     
            self.leverage = 15         
            self.stop_atr = 2.0       
            self.pyramid_max = 5      
        
        # --- Adaptive Parameters (Regime switching) ---
        self.bear_entry_window = 48   # 24 hours (faster for shorts)
        self.bear_exit_window = 24    # 12 hours
        self.bear_high_exit_window = 12 # 6 hours (very fast for shorts)
        
        self.stop_atr = 3.0           # Increased for more breathing room
        self.adx_threshold = 25       # Strong trend required
        self.choppy_adx_threshold = 20 # Below this, avoid trading if possible
        
        # --- Legacy Parameters ---
        self.st_length = 10
        self.st_factor = 3.0
        
    def populate_indicators(self, df):
        # Ensure numeric
        cols = ['open', 'high', 'low', 'close']
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
        
        if self.mode in ['robust_extreme', 'robust_dual', 'robust_adaptive', 'extreme_growth', 'ultra_growth']:
            # Donchian Channels (Standard/Bull)
            df['donchian_high'] = df['high'].rolling(window=self.entry_window).max().shift(1).fillna(0)
            df['donchian_low'] = df['low'].rolling(window=self.exit_window).min().shift(1).fillna(0)
            df['donchian_low_entry'] = df['low'].rolling(window=self.entry_window).min().shift(1).fillna(0)
            
            # Donchian Channels (Bear/Fast)
            df['bear_high_entry'] = df['high'].rolling(window=self.bear_entry_window).max().shift(1)
            df['bear_low_entry'] = df['low'].rolling(window=self.bear_entry_window).min().shift(1)
            df['bear_fast_low'] = df['low'].rolling(window=24).min().shift(1) # Fast 12h window
            df['bear_high_exit'] = df['high'].rolling(window=self.bear_high_exit_window if hasattr(self, 'bear_high_exit_window') else self.bear_exit_window).max().shift(1)
            df['bear_low_exit'] = df['low'].rolling(window=self.bear_exit_window).min().shift(1)
            
            # Super Exit for Extreme Growth
            df['super_exit_long'] = df['low'].rolling(window=12).min().shift(1)
            df['super_exit_short'] = df['high'].rolling(window=12).max().shift(1)
            
            # Slow Bull Exit for staying in trends longer
            df['bull_exit_slow'] = df['low'].rolling(window=48).min().shift(1) # 24h window

            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14).fillna(0)
            adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
            df['adx'] = adx_df['ADX_14'].fillna(0) if adx_df is not None else 0
            # ADX Slope: to detect if trend is strengthening or weakening
            df['adx_slope'] = df['adx'].diff(3) 
            
            # Volatility Filter: ATR as % of Price
            df['atr_pct'] = (df['atr'] / df['close']) * 100
            
            e50 = ta.ema(df['close'], length=50)
            df['ema_50'] = e50.fillna(0) if e50 is not None else 0
            e200 = ta.ema(df['close'], length=200)
            df['ema_200'] = e200.fillna(0) if e200 is not None else 0
            e1000 = ta.ema(df['close'], length=1000)
            df['ema_1000'] = e1000.fillna(0) if e1000 is not None else 0
            rsi_val = ta.rsi(df['close'], length=14)
            df['rsi'] = rsi_val.fillna(0) if rsi_val is not None else 0
            # EMA Slopes
            df['ema_50_slope'] = df['ema_50'].diff(3)
            
            # EMA Alignment Quality (0 to 1)
            # 1.0 = perfect alignment (50 > 200 > 1000), 0 = messy
            df['ema_quality'] = 0.0 # Float
            df.loc[(df['ema_50'] > df['ema_200']) & (df['ema_200'] > df['ema_1000']), 'ema_quality'] = 1.0
            df.loc[(df['ema_50'] < df['ema_200']) & (df['ema_200'] < df['ema_1000']), 'ema_quality'] = 1.0
            # Intermediate quality (only two aligned)
            df.loc[(df['ema_quality'] == 0.0) & ((df['ema_50'] > df['ema_200']) | (df['ema_200'] > df['ema_1000'])), 'ema_quality'] = 0.5
            
        elif self.mode == 'legacy_supertrend':
            st = ta.supertrend(df['high'], df['low'], df['close'], length=self.st_length, multiplier=self.st_factor)
            if st is not None:
                df = pd.concat([df, st], axis=1)
                df['supertrend_dir'] = df[[c for c in df.columns if c.startswith('SUPERTd')][0]]
                df['supertrend_val'] = df[[c for c in df.columns if c.startswith('SUPERT_')][0]]
            df['ema_long'] = ta.ema(df['close'], length=200)
            df['adx'] = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14']
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
            
        return df

    def backtest(self, df, start_date=None, end_date=None, initial_balance=10000, fee_rate=0.0005, verbose=False):
        self.fee_rate = fee_rate
        if self.mode == 'robust_extreme':
            return self._backtest_robust_extreme(df, start_date, end_date, initial_balance, verbose)
        elif self.mode == 'robust_dual':
            return self._backtest_robust_dual(df, start_date, end_date, initial_balance, verbose)
        elif self.mode in ['robust_adaptive', 'extreme_growth', 'ultra_growth']:
            return self._backtest_adaptive(df, start_date, end_date, initial_balance, verbose)
        else:
            return self._backtest_legacy(df, start_date, end_date, initial_balance, verbose)

    def _backtest_robust_extreme(self, df, start_date, end_date, initial_balance, verbose):
        # (Existing RobustExtreme logic)
        backtest_df = self._slice_data(df, start_date, end_date)
        if len(backtest_df) == 0: return initial_balance, [], [initial_balance]

        balance = initial_balance
        position = None 
        entry_price = 0
        stop_price = 0
        peak_price = 0
        trades = []
        equity_curve = [initial_balance]
        fee_rate = self.fee_rate 
        pyramid_level = 0
        avg_entry_price = 0
        total_position_size = 0 
        risk_per_trade = 0.10 
        base_ratio = 0.5     
        consecutive_losses = 0
        
        start_idx = max(self.entry_window, 200)
        current_leverage = self.base_leverage
        
        for i in range(start_idx, len(backtest_df)):
            curr = backtest_df.iloc[i]
            if balance <= 0: break

            if position == 'long':
                # Pyramiding (Long)
                if pyramid_level < 2 and curr['close'] > avg_entry_price * 1.02:
                    additional_risk = risk_per_trade * 0.5
                    dist_to_stop = (curr['close'] - stop_price) / curr['close']
                    if dist_to_stop <= 0: dist_to_stop = 0.01
                    risk_amount = balance * additional_risk
                    additional_margin = risk_amount / dist_to_stop
                    max_margin = balance * current_leverage
                    current_margin = total_position_size * avg_entry_price
                    if current_margin + additional_margin > max_margin: additional_margin = max_margin - current_margin
                    if additional_margin > 0:
                        balance -= additional_margin * fee_rate
                        added_amount = additional_margin / curr['close']
                        total_position_size += added_amount
                        avg_entry_price = ((avg_entry_price * (total_position_size - added_amount)) + additional_margin) / total_position_size
                        pyramid_level += 1
                        stop_price = max(stop_price, avg_entry_price * 1.002) 
                
                # Ratchet
                if curr['high'] > peak_price:
                    peak_price = curr['high']
                    roi_leveraged = ((peak_price - avg_entry_price) / avg_entry_price) * current_leverage
                    if roi_leveraged > 1.5: stop_price = max(stop_price, peak_price * 0.99)
                    elif roi_leveraged > 0.8: stop_price = max(stop_price, peak_price * 0.98)
                    elif roi_leveraged > 0.3: stop_price = max(stop_price, avg_entry_price * 1.01)

                # Exit
                triggered_exit = False
                if curr['low'] <= stop_price:
                    exit_price, exit_type, triggered_exit = stop_price, 'stop_loss', True
                elif curr['close'] < curr['donchian_low']:
                    exit_price, exit_type, triggered_exit = curr['close'], 'signal_exit', True
                    
                if triggered_exit:
                    pnl = (exit_price - avg_entry_price) * total_position_size
                    balance += pnl - (exit_price * total_position_size * fee_rate)
                    roi = (exit_price - avg_entry_price) / avg_entry_price * 100 * current_leverage
                    trades.append({'date': curr.name, 'type': 'sell', 'reason': exit_type, 'entry_price': avg_entry_price, 'exit_price': exit_price, 'roi': roi, 'balance': balance})
                    
                    if roi < 0: consecutive_losses += 1
                    else: consecutive_losses = 0
                    
                    if hasattr(self, '_last_partial_idx'): del self._last_partial_idx
                    
                    position, pyramid_level, total_position_size = None, 0, 0
                    equity_curve.append(balance)
                    continue

            if position is None and balance > 10:
                if curr['close'] > curr['donchian_high'] and curr['close'] > curr['ema_50'] and curr['adx'] > 15:
                    position, pyramid_level = 'long', 1
                    margin = balance * base_ratio * self.base_leverage
                    entry_price = avg_entry_price = curr['close']
                    stop_price = entry_price - (curr['atr'] * self.stop_atr)
                    balance -= margin * fee_rate
                    total_position_size, peak_price = margin / entry_price, entry_price
            
            equity_curve.append(balance)
        return balance, trades, equity_curve

    def _backtest_robust_dual(self, df, start_date, end_date, initial_balance, verbose):
        backtest_df = self._slice_data(df, start_date, end_date)
        if len(backtest_df) == 0: return initial_balance, [], [initial_balance]

        balance = initial_balance
        position = None # 'long', 'short', or None
        entry_price = 0
        stop_price = 0
        peak_price = 0 # peak for long, valley for short
        trades = []
        equity_curve = [initial_balance]
        fee_rate = self.fee_rate 
        pyramid_level = 0
        avg_entry_price = 0
        total_position_size = 0 
        risk_per_trade = 0.10 
        base_ratio = 0.5     
        
        start_idx = max(self.entry_window, 200)
        
        for i in range(start_idx, len(backtest_df)):
            curr = backtest_df.iloc[i]
            if balance <= 0: break

            if position == 'long':
                # Pyramiding (Long)
                if pyramid_level < 2 and curr['close'] > avg_entry_price * 1.02:
                    additional_risk = risk_per_trade * 0.5
                    dist_to_stop = (curr['close'] - stop_price) / curr['close']
                    if dist_to_stop <= 0: dist_to_stop = 0.01
                    risk_amount = balance * additional_risk
                    additional_margin = risk_amount / dist_to_stop
                    max_margin = balance * self.base_leverage
                    current_margin = total_position_size * avg_entry_price
                    if current_margin + additional_margin > max_margin: additional_margin = max_margin - current_margin
                    if additional_margin > 0:
                        balance -= additional_margin * fee_rate
                        added_amount = additional_margin / curr['close']
                        total_position_size += added_amount
                        avg_entry_price = ((avg_entry_price * (total_position_size - added_amount)) + additional_margin) / total_position_size
                        pyramid_level += 1
                        stop_price = max(stop_price, avg_entry_price * 1.002) 
                
                # Ratchet (Long)
                if curr['high'] > peak_price:
                    peak_price = curr['high']
                    roi_leveraged = ((peak_price - avg_entry_price) / avg_entry_price) * self.base_leverage
                    if roi_leveraged > 2.0: stop_price = max(stop_price, peak_price * 0.99)
                    elif roi_leveraged > 1.0: stop_price = max(stop_price, peak_price * 0.98)
                    elif roi_leveraged > 0.5: stop_price = max(stop_price, avg_entry_price * 1.02)

                # Exit (Long)
                triggered_exit = False
                if curr['low'] <= stop_price:
                    exit_price, exit_type, triggered_exit = stop_price, 'stop_loss', True
                elif curr['close'] < curr['donchian_low']:
                    exit_price, exit_type, triggered_exit = curr['close'], 'signal_exit', True
                    
                if triggered_exit:
                    pnl = (exit_price - avg_entry_price) * total_position_size
                    balance += pnl - (exit_price * total_position_size * fee_rate)
                    trades.append({'date': curr.name, 'type': 'sell', 'reason': exit_type, 'entry_price': avg_entry_price, 'exit_price': exit_price, 'roi': (exit_price - avg_entry_price) / avg_entry_price * 100 * self.base_leverage, 'balance': balance})
                    position, pyramid_level, total_position_size = None, 0, 0
                    equity_curve.append(balance)
                    continue

            elif position == 'short':
                # Pyramiding (Short)
                if pyramid_level < 2 and curr['close'] < avg_entry_price * 0.98:
                    additional_risk = risk_per_trade * 0.5
                    dist_to_stop = (stop_price - curr['close']) / curr['close']
                    if dist_to_stop <= 0: dist_to_stop = 0.01
                    risk_amount = balance * additional_risk
                    additional_margin = risk_amount / dist_to_stop
                    max_margin = balance * self.base_leverage
                    current_margin = total_position_size * avg_entry_price
                    if current_margin + additional_margin > max_margin: additional_margin = max_margin - current_margin
                    if additional_margin > 0:
                        balance -= additional_margin * fee_rate
                        added_amount = additional_margin / curr['close']
                        total_position_size += added_amount
                        avg_entry_price = ((avg_entry_price * (total_position_size - added_amount)) + additional_margin) / total_position_size
                        pyramid_level += 1
                        stop_price = min(stop_price, avg_entry_price * 0.998)

                # Ratchet (Short)
                if curr['low'] < peak_price: # peak_price is 'valley' here
                    peak_price = curr['low']
                    roi_leveraged = ((avg_entry_price - peak_price) / avg_entry_price) * self.base_leverage
                    if roi_leveraged > 2.0: stop_price = min(stop_price, peak_price * 1.01)
                    elif roi_leveraged > 1.0: stop_price = min(stop_price, peak_price * 1.02)
                    elif roi_leveraged > 0.5: stop_price = min(stop_price, avg_entry_price * 0.98)

                # Exit (Short)
                triggered_exit = False
                if curr['high'] >= stop_price:
                    exit_price, exit_type, triggered_exit = stop_price, 'stop_loss', True
                elif curr['close'] > curr['donchian_high']: # Exit on trend reversal
                    exit_price, exit_type, triggered_exit = curr['close'], 'signal_exit', True

                if triggered_exit:
                    pnl = (avg_entry_price - exit_price) * total_position_size
                    balance += pnl - (exit_price * total_position_size * fee_rate)
                    trades.append({'date': curr.name, 'type': 'buy', 'reason': exit_type, 'entry_price': avg_entry_price, 'exit_price': exit_price, 'roi': (avg_entry_price - exit_price) / avg_entry_price * 100 * self.base_leverage, 'balance': balance})
                    position, pyramid_level, total_position_size = None, 0, 0
                    equity_curve.append(balance)
                    continue

            # Entry Logic
            if position is None and balance > 10:
                # Long Entry
                if curr['close'] > curr['donchian_high'] and curr['close'] > curr['ema_50'] and curr['adx'] > self.adx_threshold:
                    position, pyramid_level = 'long', 1
                    margin = balance * base_ratio * self.base_leverage
                    entry_price = avg_entry_price = curr['close']
                    stop_price = entry_price - (curr['atr'] * self.stop_atr)
                    balance -= margin * fee_rate
                    total_position_size, peak_price = margin / entry_price, entry_price
                
                # Short Entry
                elif curr['close'] < curr['donchian_low_entry'] and curr['close'] < curr['ema_50'] and curr['adx'] > self.adx_threshold:
                    position, pyramid_level = 'short', 1
                    margin = balance * base_ratio * self.base_leverage
                    entry_price = avg_entry_price = curr['close']
                    stop_price = entry_price + (curr['atr'] * self.stop_atr)
                    balance -= margin * fee_rate
                    total_position_size, peak_price = margin / entry_price, entry_price # peak_price is valley
            
            equity_curve.append(balance)
        return balance, trades, equity_curve

    def _backtest_adaptive(self, df, start_date, end_date, initial_balance, verbose):
        """
        Adaptive switching between Bull module and Bear module.
        Bull: Long-only, medium windows (Optimized for 2025 style)
        Bear: Long/Short, fast windows (Optimized for 2021-2022 style)
        """
        # Reset state attributes at the start of each backtest run
        for attr in ['_partial_0_hit', '_partial_1_hit', '_partial_2_hit']:
            if hasattr(self, attr):
                delattr(self, attr)

        backtest_df = self._slice_data(df, start_date, end_date)
        if len(backtest_df) == 0: return initial_balance, [], [initial_balance]

        balance = initial_balance
        position = None # 'long', 'short', or None
        entry_price = 0
        stop_price = 0
        peak_price = 0
        trades = []
        equity_curve = [initial_balance]
        fee_rate = self.fee_rate 
        pyramid_level = 0
        avg_entry_price = 0
        total_position_size = 0 
        risk_per_trade = 0.05  # 5% risk per trade for pyramiding
        consecutive_losses = 0
        
        # Lock parameters for the current trade
        trade_leverage = 0
        trade_stop_atr = 0
        
        # Fix: Start index should handle cases where data is already populated
        # Only skip if required indicators are NaN
        start_idx = 0
        for i in range(len(backtest_df)):
            curr = backtest_df.iloc[i]
            if not pd.isna(curr['ema_1000']) and not pd.isna(curr['adx']):
                start_idx = i
                break
        
        # Risk management parameters
        if self.mode == 'ultra_growth':
            risk_per_trade_pct = 0.10  # 10% 리스크
            max_margin_ratio = 0.95
        elif self.mode == 'extreme_growth':
            risk_per_trade_pct = 0.09
            max_margin_ratio = 0.95
        else:
            risk_per_trade_pct = 0.02
            max_margin_ratio = 0.3
        
        # Performance tracking
        consecutive_losses = 0
        last_trade_bar = -100 # Initialize
        
        for i in range(start_idx, len(backtest_df)):
            curr = backtest_df.iloc[i]
            if balance <= 1: break

            # Regime Detection & Trending Signals
            is_bull_strict = (curr['ema_50'] > curr['ema_200']) and (curr['ema_200'] > curr['ema_1000'])
            is_bull_regime = (curr['ema_50'] > curr['ema_200'])
            is_trending = curr['adx'] > 25
            trend_strengthening = curr['adx_slope'] > 0
            
            # Adaptive Strategy: Low Volatility Filter
            # 2025년과 같은 저변동성 횡보장에서 잦은 손절을 방지하기 위함
            is_low_vol = curr['atr_pct'] < 0.35 # Slightly more relaxed
            
            # Market Strength
            market_strength = 0.0
            if curr['ema_quality'] > 0.8: market_strength += 0.4
            if curr['adx'] > 30: market_strength += 0.3
            if trend_strengthening: market_strength += 0.3
            
            is_strong_bull = is_bull_regime and market_strength >= 0.6

            # Dynamic Parameters
            if self.mode in ['extreme_growth', 'ultra_growth']:
                
                # Ultra Growth: 더 공격적인 레버리지
                if self.mode == 'ultra_growth':
                    if curr['atr_pct'] < 1.0: base_lev = 25.0 
                    elif curr['atr_pct'] < 2.0: base_lev = 20.0
                    elif curr['atr_pct'] < 3.0: base_lev = 15.0
                    else: base_lev = 10.0
                    max_lev = 25.0
                else:
                    if curr['atr_pct'] < 1.0: base_lev = 25.0 
                    elif curr['atr_pct'] < 2.0: base_lev = 20.0
                    elif curr['atr_pct'] < 4.0: base_lev = 15.0
                    else: base_lev = 10.0
                    max_lev = 30.0
                
                # High Confidence Multiplier
                conf_score = 0.0
                if curr['adx'] > 25: conf_score += 0.1
                if curr['adx'] > 40: conf_score += 0.15
                if curr['ema_quality'] > 0.9: conf_score += 0.25
                
                current_leverage = base_lev * (0.8 + conf_score)
                current_leverage = max(5.0, min(max_lev, current_leverage))
                
                # Adaptive Stop ATR (ultra는 더 타이트)
                if self.mode == 'ultra_growth':
                    current_stop_atr = 1.5 + (curr['atr_pct'] * 0.05)
                else:
                    # Adaptive: 저변동성 구간에서는 손절폭을 넓히고, 강세장에서는 중간 정도 유지
                    if is_low_vol:
                        current_stop_atr = 2.8 + (curr['atr_pct'] * 0.2) # 저변동성 휩소 방지
                    elif is_strong_bull:
                        current_stop_atr = 2.4 + (curr['atr_pct'] * 0.1) # 강세장에서는 적절히 타이트
                    else:
                        current_stop_atr = 2.2 + (curr['atr_pct'] * 0.1)
                
                is_volatility_ok = curr['atr_pct'] < 7.0
                bear_entry_sig = curr['bear_low_entry']
                
                # Risk-based Position Sizing
                # Risk 5.7% of balance on each trade
                stop_dist_pct = (curr['atr'] * current_stop_atr) / curr['close']
                if stop_dist_pct < 0.005: stop_dist_pct = 0.005
                
                # Margin required to risk 'risk_per_trade_pct' given 'stop_dist_pct' and 'leverage'
                # Risk = Margin * Leverage * StopDist
                # Margin = Risk / (Leverage * StopDist)
                current_base_ratio = risk_per_trade_pct / (current_leverage * stop_dist_pct)
                current_base_ratio = min(max_margin_ratio, current_base_ratio)
            else:
                is_bull_regime = is_bull_strict
                current_leverage = 3.0 if is_bull_regime else 1.0
                current_stop_atr = 3.0 if is_bull_regime else 1.5 
                is_volatility_ok = True
                bear_entry_sig = curr['bear_low_entry']
                current_base_ratio = 0.3 if is_bull_regime else 0.15
            
            if position == 'long':
                # Liquidation Check - 레버리지 기반 청산가 계산
                # 청산가 = 진입가 * (1 - 1/레버리지 + 유지증거금율)
                # 바이낸스 유지증거금율 약 0.4%~0.5%
                maint_margin_rate = 0.005
                liquidation_price = avg_entry_price * (1 - (1 / trade_leverage) + maint_margin_rate)
                
                if curr['low'] <= liquidation_price:
                    # 청산 발생 - 포지션 전액 손실
                    exit_price = liquidation_price
                    # 실제 손실 계산 (증거금 전액 손실)
                    margin_used = (total_position_size * avg_entry_price) / trade_leverage
                    balance -= margin_used  # 증거금 손실
                    if balance < 0:
                        balance = 0
                    
                    trades.append({'date': curr.name, 'type': 'sell', 'reason': 'liquidation', 
                                   'entry_price': avg_entry_price, 'exit_price': exit_price, 
                                   'roi': -100.0, 'balance': balance})
                    
                    # 상태 초기화 (break 대신 continue로 거래 계속)
                    if hasattr(self, '_partial_0_hit'): del self._partial_0_hit
                    if hasattr(self, '_partial_1_hit'): del self._partial_1_hit
                    if hasattr(self, '_partial_2_hit'): del self._partial_2_hit
                    position, pyramid_level, total_position_size = None, 0, 0
                    equity_curve.append(balance)
                    if balance <= 1:  # 잔고 거의 없으면 종료
                        break
                    continue

                # Partial Profit Taking (Long)
                roi_unleveraged = (curr['close'] - avg_entry_price) / avg_entry_price
                
                if self.mode == 'extreme_growth':
                    # Adaptive Partial Profit: 강한 상승장에서는 익절 비중을 줄임
                    p_ratio = 0.08 if is_strong_bull else 0.15 # 15% -> 8%

                    # Capture larger moves but lock in faster
                    # Target 1: 50% leveraged ROI -> Sell p_ratio
                    if roi_unleveraged * trade_leverage > 0.5 and not hasattr(self, '_partial_0_hit'):
                        sell_amt = total_position_size * p_ratio
                        pnl = (curr['close'] - avg_entry_price) * sell_amt
                        balance += pnl - (curr['close'] * sell_amt * fee_rate)
                        total_position_size -= sell_amt
                        trades.append({'date': curr.name, 'type': 'sell', 'reason': f'partial_profit_50pct_{p_ratio*100:.0f}', 'entry_price': avg_entry_price, 'exit_price': curr['close'], 'roi': roi_unleveraged * 100 * trade_leverage, 'balance': balance})
                        self._partial_0_hit = True

                    # Target 2: 120% leveraged ROI -> Sell p_ratio + Move to Break-even
                    if roi_unleveraged * trade_leverage > 1.2 and not hasattr(self, '_partial_1_hit'):
                        sell_amt = total_position_size * p_ratio
                        pnl = (curr['close'] - avg_entry_price) * sell_amt
                        balance += pnl - (curr['close'] * sell_amt * fee_rate)
                        total_position_size -= sell_amt
                        trades.append({'date': curr.name, 'type': 'sell', 'reason': f'partial_profit_120pct_{p_ratio*100:.0f}', 'entry_price': avg_entry_price, 'exit_price': curr['close'], 'roi': roi_unleveraged * 100 * trade_leverage, 'balance': balance})
                        stop_price = max(stop_price, avg_entry_price * 1.01)
                        self._partial_1_hit = True

                    # Target 3: 300% leveraged ROI -> Sell 20% (or 10% in strong bull)
                    if roi_unleveraged * trade_leverage > 3.0 and not hasattr(self, '_partial_2_hit'):
                        sell_amt = total_position_size * (0.1 if is_strong_bull else 0.2)
                        pnl = (curr['close'] - avg_entry_price) * sell_amt
                        balance += pnl - (curr['close'] * sell_amt * fee_rate)
                        total_position_size -= sell_amt
                        trades.append({'date': curr.name, 'type': 'sell', 'reason': 'partial_profit_300pct', 'entry_price': avg_entry_price, 'exit_price': curr['close'], 'roi': roi_unleveraged * 100 * trade_leverage, 'balance': balance})
                        # Move stop to lock in 70% of current unleveraged profit
                        stop_price = max(stop_price, avg_entry_price * (1 + roi_unleveraged * 0.7))
                        self._partial_2_hit = True
                else:
                    trigger_roi = 0.5 if trade_leverage > 1 else 0.15
                    if roi_unleveraged * trade_leverage > trigger_roi and pyramid_level >= 1:
                        sell_amt = total_position_size * 0.3
                        pnl = (curr['close'] - avg_entry_price) * sell_amt
                        balance += pnl - (curr['close'] * sell_amt * fee_rate)
                        total_position_size -= sell_amt
                        trades.append({'date': curr.name, 'type': 'sell', 'reason': 'partial_profit', 'entry_price': avg_entry_price, 'exit_price': curr['close'], 'roi': roi_unleveraged * 100 * trade_leverage, 'balance': balance})
                        stop_price = max(stop_price, avg_entry_price * 1.02)

                # Pyramiding (Long)
                pyramid_max = 6 if self.mode == 'extreme_growth' else 3 
                pyramid_trigger = 1.05 if self.mode == 'extreme_growth' else 1.04 
                if pyramid_level < pyramid_max and curr['close'] > avg_entry_price * pyramid_trigger and is_trending:
                    # Risk-based pyramiding
                    additional_risk_pct = risk_per_trade_pct * 0.5
                    dist_to_stop = (curr['close'] - stop_price) / curr['close']
                    if dist_to_stop <= 0.005: dist_to_stop = 0.005
                    
                    added_pos_value = (balance * additional_risk_pct) / dist_to_stop
                    added_margin = added_pos_value / trade_leverage
                    
                    if added_margin > balance * 0.2: added_margin = balance * 0.2 # Cap addition
                    
                    if added_margin > 0:
                        balance -= added_margin * fee_rate
                        added_amount = (added_margin * trade_leverage) / curr['close']
                        total_position_size += added_amount
                        avg_entry_price = ((avg_entry_price * (total_position_size - added_amount)) + (added_amount * curr['close'])) / total_position_size
                        pyramid_level += 1
                
                # Ratchet (Long)
                if curr['high'] > peak_price:
                    peak_price = curr['high']
                    roi_leveraged = ((peak_price - avg_entry_price) / avg_entry_price) * trade_leverage
                    
                    if self.mode == 'extreme_growth':
                        # Break-even logic: Move stop to entry faster
                        if roi_leveraged > 0.08: stop_price = max(stop_price, avg_entry_price * 1.002)
                        
                        # Adaptive Trailing Stop: 강한 상승장에서는 더 넓은 여유를 줌
                        trail_tightness = 0.98 if not is_strong_bull else 0.94 # 강세장 6%
                        trail_mid = 0.96 if not is_strong_bull else 0.92 # 강세장 8%
                        trail_loose = 0.94 if not is_strong_bull else 0.90 # 강세장 10%

                        if roi_leveraged > 4.0: stop_price = max(stop_price, peak_price * trail_loose) 
                        elif roi_leveraged > 2.0: stop_price = max(stop_price, peak_price * trail_mid)
                        elif roi_leveraged > 1.0: stop_price = max(stop_price, peak_price * trail_tightness)
                        elif roi_leveraged > 0.4: stop_price = max(stop_price, avg_entry_price * 1.05)
                    else:
                        if roi_leveraged > 1.2: stop_price = max(stop_price, peak_price * 0.985)
                        elif roi_leveraged > 0.6: stop_price = max(stop_price, peak_price * 0.975)
                        elif roi_leveraged > 0.2: stop_price = max(stop_price, avg_entry_price * 1.01)

                # Exit
                triggered_exit = False
                if curr['low'] <= stop_price:
                    exit_price, exit_type, triggered_exit = stop_price, 'stop_loss', True
                else:
                    if self.mode == 'extreme_growth':
                        if is_strong_bull:
                            # 강한 상승장에서는 bull_exit_slow(48시간 저점) 사용하여 길게 보유
                            exit_sig = curr['bull_exit_slow']
                        elif curr['adx'] > 50 and trend_strengthening:
                            exit_sig = curr['super_exit_long']
                        else:
                            exit_sig = curr['donchian_low']
                    else:
                        exit_sig = curr['donchian_low'] if is_bull_regime else curr['bear_low_exit']
                    
                    if curr['close'] < exit_sig:
                        exit_price, exit_type, triggered_exit = curr['close'], 'signal_exit', True
                    
                if triggered_exit:
                    pnl = (exit_price - avg_entry_price) * total_position_size
                    roi = (exit_price - avg_entry_price) / avg_entry_price * 100 * trade_leverage
                    
                    # ROI가 -100% 이하면 청산 처리 (증거금 전액 손실)
                    if roi <= -100:
                        margin_used = (total_position_size * avg_entry_price) / trade_leverage
                        balance -= margin_used
                        if balance < 0: balance = 0
                        roi = -100.0
                        exit_type = 'liquidation'
                    else:
                        balance += pnl - (exit_price * total_position_size * fee_rate)
                    
                    trades.append({'date': curr.name, 'type': 'sell', 'reason': exit_type, 'entry_price': avg_entry_price, 'exit_price': exit_price, 'roi': roi, 'balance': balance})
                    
                    if roi < -10.0: consecutive_losses += 1
                    else: consecutive_losses = 0
                    last_trade_bar = i
                    
                    if hasattr(self, '_partial_0_hit'): del self._partial_0_hit
                    if hasattr(self, '_partial_1_hit'): del self._partial_1_hit
                    if hasattr(self, '_partial_2_hit'): del self._partial_2_hit
                    
                    position, pyramid_level, total_position_size = None, 0, 0
                    equity_curve.append(balance)
                    if balance <= 1:
                        break
                    continue

            elif position == 'short':
                # Liquidation Check (Short) - 레버리지 기반 청산가 계산
                # 숏 청산가 = 진입가 * (1 + 1/레버리지 - 유지증거금율)
                maint_margin_rate = 0.005
                liquidation_price = avg_entry_price * (1 + (1 / trade_leverage) - maint_margin_rate)
                
                if curr['high'] >= liquidation_price:
                    # 청산 발생 - 포지션 전액 손실
                    exit_price = liquidation_price
                    # 실제 손실 계산 (증거금 전액 손실)
                    margin_used = (total_position_size * avg_entry_price) / trade_leverage
                    balance -= margin_used  # 증거금 손실
                    if balance < 0:
                        balance = 0
                    
                    trades.append({'date': curr.name, 'type': 'buy', 'reason': 'liquidation', 
                                   'entry_price': avg_entry_price, 'exit_price': exit_price, 
                                   'roi': -100.0, 'balance': balance})
                    
                    # 상태 초기화
                    if hasattr(self, '_partial_0_hit'): del self._partial_0_hit
                    if hasattr(self, '_partial_1_hit'): del self._partial_1_hit
                    if hasattr(self, '_partial_2_hit'): del self._partial_2_hit
                    position, pyramid_level, total_position_size = None, 0, 0
                    equity_curve.append(balance)
                    if balance <= 1:
                        break
                    continue

                # Partial Profit Taking (Short)
                roi_unleveraged = (avg_entry_price - curr['close']) / avg_entry_price
                
                if self.mode == 'extreme_growth':
                    # Aggressive partial profit for short
                    # Target 1: 40% leveraged ROI -> Sell 15%
                    if roi_unleveraged * trade_leverage > 0.4 and not hasattr(self, '_partial_0_hit'):
                        sell_amt = total_position_size * 0.15
                        pnl = (avg_entry_price - curr['close']) * sell_amt
                        balance += pnl - (curr['close'] * sell_amt * fee_rate)
                        total_position_size -= sell_amt
                        trades.append({'date': curr.name, 'type': 'buy', 'reason': 'partial_profit_40pct_short', 'entry_price': avg_entry_price, 'exit_price': curr['close'], 'roi': roi_unleveraged * 100 * trade_leverage, 'balance': balance})
                        self._partial_0_hit = True

                    # Target 2: 100% leveraged ROI -> Sell 15% + Move to Break-even
                    if roi_unleveraged * trade_leverage > 1.0 and not hasattr(self, '_partial_1_hit'):
                        sell_amt = total_position_size * 0.15
                        pnl = (avg_entry_price - curr['close']) * sell_amt
                        balance += pnl - (curr['close'] * sell_amt * fee_rate)
                        total_position_size -= sell_amt
                        trades.append({'date': curr.name, 'type': 'buy', 'reason': 'partial_profit_100pct_short', 'entry_price': avg_entry_price, 'exit_price': curr['close'], 'roi': roi_unleveraged * 100 * trade_leverage, 'balance': balance})
                        stop_price = min(stop_price, avg_entry_price * 0.99)
                        self._partial_1_hit = True
                    
                    # Target 3: 250% leveraged ROI -> Sell 20%
                    if roi_unleveraged * trade_leverage > 2.5 and not hasattr(self, '_partial_2_hit'):
                        sell_amt = total_position_size * 0.2
                        pnl = (avg_entry_price - curr['close']) * sell_amt
                        balance += pnl - (curr['close'] * sell_amt * fee_rate)
                        total_position_size -= sell_amt
                        trades.append({'date': curr.name, 'type': 'buy', 'reason': 'partial_profit_250pct_short', 'entry_price': avg_entry_price, 'exit_price': curr['close'], 'roi': roi_unleveraged * 100 * trade_leverage, 'balance': balance})
                        # Move stop to lock in 70% of current unleveraged profit
                        stop_price = min(stop_price, avg_entry_price * (1 - roi_unleveraged * 0.7))
                        self._partial_2_hit = True
                else:
                    trigger_roi = 0.5 if trade_leverage > 1 else 0.15
                    if roi_unleveraged * trade_leverage > trigger_roi and pyramid_level >= 1:
                        sell_amt = total_position_size * 0.3
                        pnl = (avg_entry_price - curr['close']) * sell_amt
                        balance += pnl - (curr['close'] * sell_amt * fee_rate)
                        total_position_size -= sell_amt
                        trades.append({'date': curr.name, 'type': 'buy', 'reason': 'partial_profit', 'entry_price': avg_entry_price, 'exit_price': curr['close'], 'roi': roi_unleveraged * 100 * trade_leverage, 'balance': balance})
                        stop_price = min(stop_price, avg_entry_price * 0.98)

                # Pyramiding (Short)
                pyramid_max = 5 if self.mode == 'extreme_growth' else 2
                pyramid_trigger = 0.96 if self.mode == 'extreme_growth' else 0.97 
                if pyramid_level < pyramid_max and curr['close'] < avg_entry_price * pyramid_trigger and is_trending:
                    # Risk-based pyramiding
                    additional_risk_pct = risk_per_trade_pct * 0.5
                    dist_to_stop = (stop_price - curr['close']) / curr['close']
                    if dist_to_stop <= 0.005: dist_to_stop = 0.005
                    
                    added_pos_value = (balance * additional_risk_pct) / dist_to_stop
                    added_margin = added_pos_value / trade_leverage
                    
                    if added_margin > balance * 0.2: added_margin = balance * 0.2 # Cap addition
                    
                    if added_margin > 0:
                        balance -= added_margin * fee_rate
                        added_amount = (added_margin * trade_leverage) / curr['close']
                        total_position_size += added_amount
                        avg_entry_price = ((avg_entry_price * (total_position_size - added_amount)) + (added_amount * curr['close'])) / total_position_size
                        pyramid_level += 1
                        stop_price = min(stop_price, avg_entry_price * 0.998)

                # Ratchet (Short)
                if curr['low'] < peak_price: 
                    peak_price = curr['low']
                    roi_leveraged = ((avg_entry_price - peak_price) / avg_entry_price) * trade_leverage
                    
                    if self.mode == 'extreme_growth':
                        # Break-even logic for short: Move stop to entry faster
                        if roi_leveraged > 0.08: stop_price = min(stop_price, avg_entry_price * 0.998)
                        
                        if roi_leveraged > 4.0: stop_price = min(stop_price, peak_price * 1.05) 
                        elif roi_leveraged > 2.0: stop_price = min(stop_price, peak_price * 1.03)
                        elif roi_leveraged > 1.0: stop_price = min(stop_price, peak_price * 1.02)
                        elif roi_leveraged > 0.4: stop_price = min(stop_price, avg_entry_price * 0.95)
                        elif roi_leveraged > 0.2: stop_price = min(stop_price, avg_entry_price * 0.98)
                    else:
                        if roi_leveraged > 1.0: stop_price = min(stop_price, peak_price * 1.01)
                        elif roi_leveraged > 0.5: stop_price = min(stop_price, peak_price * 1.02)
                        elif roi_leveraged > 0.2: stop_price = min(stop_price, avg_entry_price * 0.995)

                # Exit (Short)
                triggered_exit = False
                if curr['high'] >= stop_price:
                    exit_price, exit_type, triggered_exit = stop_price, 'stop_loss', True
                else:
                    if self.mode == 'extreme_growth' and curr['adx'] > 45 and trend_strengthening:
                        exit_sig = curr['super_exit_short']
                    else:
                        exit_sig = curr['bear_high_exit']
                    
                    if curr['close'] > exit_sig:
                        exit_price, exit_type, triggered_exit = curr['close'], 'signal_exit', True

                if triggered_exit:
                    pnl = (avg_entry_price - exit_price) * total_position_size
                    roi = (avg_entry_price - exit_price) / avg_entry_price * 100 * trade_leverage
                    
                    # ROI가 -100% 이하면 청산 처리 (증거금 전액 손실)
                    if roi <= -100:
                        margin_used = (total_position_size * avg_entry_price) / trade_leverage
                        balance -= margin_used
                        if balance < 0: balance = 0
                        roi = -100.0
                        exit_type = 'liquidation'
                    else:
                        balance += pnl - (exit_price * total_position_size * fee_rate)
                    
                    trades.append({'date': curr.name, 'type': 'buy', 'reason': exit_type, 'entry_price': avg_entry_price, 'exit_price': exit_price, 'roi': roi, 'balance': balance})
                    
                    if roi < -10.0: consecutive_losses += 1
                    else: consecutive_losses = 0
                    last_trade_bar = i
                    
                    if hasattr(self, '_partial_0_hit'): del self._partial_0_hit
                    if hasattr(self, '_partial_1_hit'): del self._partial_1_hit
                    if hasattr(self, '_partial_2_hit'): del self._partial_2_hit
                    
                    position, pyramid_level, total_position_size = None, 0, 0
                    equity_curve.append(balance)
                    if balance <= 1:
                        break
                    continue

            # Entry Logic
            cool_off_bars = 48 # 24h cool-off
            is_cooling_off = (i - last_trade_bar < cool_off_bars) if consecutive_losses >= 2 else False

            if position is None and balance > 10 and is_volatility_ok and not is_cooling_off:
                # Adaptive Strategy: 저변동성 필터 (2025년 대응)
                if is_low_vol and self.mode == 'extreme_growth':
                    # 변동성이 낮을 때는 평소보다 더 높은 ADX와 이평선 정렬이 필요함
                    ad_th_base = 38
                    eq_th_base = 0.95
                else:
                    ad_th_base = 32 if self.mode == 'extreme_growth' else 25
                    eq_th_base = 0.9 if self.mode == 'extreme_growth' else 0.0

                # Long Entry Condition (More selective)
                ad_th = ad_th_base
                eq_th = eq_th_base
                
                # In bear regime, be super strict for longs
                is_long_term_bear = curr['close'] < curr['ema_200'] or curr['ema_200'] < curr['ema_1000']
                if is_long_term_bear:
                    ad_th = 40 if self.mode == 'extreme_growth' else 35
                    eq_th = 1.0 if self.mode == 'extreme_growth' else 0.5

                is_recovering = curr['close'] > curr['ema_200'] and curr['close'] > curr['ema_50']
                
                if (is_bull_regime or is_recovering) and curr['close'] > curr['donchian_high'] and curr['adx'] > ad_th and curr['ema_quality'] >= eq_th:
                    if self.mode == 'extreme_growth':
                        if curr['rsi'] > 75 and curr['adx'] < 45: continue 
                        if curr['adx'] < 35 and not trend_strengthening: continue
                    
                    position, pyramid_level = 'long', 1
                    trade_leverage = current_leverage
                    trade_stop_atr = current_stop_atr
                    margin = balance * current_base_ratio * trade_leverage
                    entry_price = avg_entry_price = curr['close']
                    stop_price = entry_price - (curr['atr'] * trade_stop_atr)
                    balance -= margin * fee_rate
                    total_position_size, peak_price = margin / entry_price, entry_price
                
                # Short Entry Condition (More selective)
                elif (not is_bull_regime or curr['close'] < curr['ema_200']) and curr['close'] < curr['ema_50'] and curr['close'] < bear_entry_sig:
                    if is_low_vol and self.mode == 'extreme_growth':
                        short_ad_th = 35 # 저변동성 숏은 더 보수적으로
                        short_eq_th = 0.95
                    else:
                        short_ad_th = 26 if self.mode == 'extreme_growth' else 25 
                        short_eq_th = 0.8 if self.mode == 'extreme_growth' else 0.0
                    
                    if curr['adx'] > short_ad_th and curr['ema_quality'] >= short_eq_th:
                        if self.mode == 'extreme_growth':
                            if curr['rsi'] < 25 and curr['adx'] < 45: continue # Relaxed from 30
                            if not trend_strengthening and curr['adx'] < 32: continue # Relaxed from 35
                        
                        position, pyramid_level = 'short', 1
                        trade_leverage = current_leverage
                        trade_stop_atr = current_stop_atr
                        margin = balance * current_base_ratio * trade_leverage
                        entry_price = avg_entry_price = curr['close']
                        stop_price = entry_price + (curr['atr'] * trade_stop_atr)
                        balance -= margin * fee_rate
                        total_position_size, peak_price = margin / entry_price, entry_price 
            
            equity_curve.append(balance)
        return balance, trades, equity_curve
 
    def _backtest_legacy(self, df, start_date, end_date, initial_balance, verbose):
        backtest_df = self._slice_data(df, start_date, end_date)
        if len(backtest_df) == 0: return initial_balance, [], [initial_balance]

        balance = initial_balance
        position = None 
        avg_entry_price = 0
        total_position_size = 0 
        trades = []
        equity_curve = [initial_balance]
        fee_rate = self.fee_rate 
        risk_per_trade = 0.03 
        pyramid_done = False
        partial_taken = False
        stop_price = 0
        
        for i in range(1, len(backtest_df)):
            curr = backtest_df.iloc[i]
            if balance <= 0: break
            
            # --- SIGNAL GENERATION ---
            st_uptrend = curr['supertrend_dir'] == 1
            long_term_bull = curr['close'] > curr['ema_long']
            strong_trend = curr['adx'] > 23 
            trend_flip_down = (curr['supertrend_dir'] == -1)
            
            # === EXIT SIGNAL ===
            if position == 'long':
                roi_curr = (curr['close'] - avg_entry_price) / avg_entry_price
                
                # 1. Profit Lock (10% Price Move -> Sell 40%)
                if roi_curr > 0.10 and not partial_taken:
                    sell_amt = total_position_size * 0.40
                    gross = curr['close'] * sell_amt
                    cost = avg_entry_price * sell_amt
                    pnl = gross - cost
                    fee = gross * fee_rate
                    balance += pnl - fee
                    total_position_size -= sell_amt
                    partial_taken = True
                    stop_price = max(stop_price, avg_entry_price * 1.01)
                    
                    trades.append({'date': curr.name, 'type': 'sell', 'reason': 'partial_profit_10pct_move', 'entry_price': avg_entry_price, 'exit_price': curr['close'], 'roi': roi_curr * 100, 'balance': balance})

                # 2. Main Exit: Trend Flip
                if trend_flip_down:
                    exit_price = curr['close']
                    pnl = (exit_price - avg_entry_price) * total_position_size
                    balance += pnl - (exit_price * total_position_size * fee_rate)
                    trades.append({'date': curr.name, 'type': 'sell', 'reason': 'supertrend_flip', 'entry_price': avg_entry_price, 'exit_price': exit_price, 'roi': (exit_price - avg_entry_price) / avg_entry_price * 100, 'balance': balance})
                    position, total_position_size, pyramid_done, partial_taken = None, 0, False, False
                    equity_curve.append(balance)
                    continue
                    
                # 3. Stop Hit (Safety)
                if curr['low'] < stop_price:
                    exit_price = stop_price
                    pnl = (exit_price - avg_entry_price) * total_position_size
                    balance += pnl - (exit_price * total_position_size * fee_rate)
                    trades.append({'date': curr.name, 'type': 'sell', 'reason': 'stop_loss', 'entry_price': avg_entry_price, 'exit_price': exit_price, 'roi': (exit_price - avg_entry_price) / avg_entry_price * 100, 'balance': balance})
                    position, total_position_size, pyramid_done, partial_taken = None, 0, False, False
                    equity_curve.append(balance)
                    continue

                # Pyramiding
                if not pyramid_done and not partial_taken and curr['close'] > avg_entry_price * 1.015:
                    add_risk_val = balance * 0.015
                    dist = (curr['atr'] * 3) / curr['close']
                    margin_add = (add_risk_val / dist) if dist > 0 else 0
                    available = (balance * self.base_leverage) - (total_position_size * avg_entry_price)
                    if margin_add > available: margin_add = available
                    if margin_add > 0:
                        balance -= margin_add * fee_rate
                        amount_add = margin_add / curr['close']
                        total_cost = (avg_entry_price * total_position_size) + margin_add
                        total_position_size += amount_add
                        avg_entry_price = total_cost / total_position_size
                        pyramid_done = True
            
            # === ENTRY SIGNAL ===
            if position is None and balance >= 10:
                if st_uptrend and long_term_bull and strong_trend:
                    position = 'long'
                    entry_price = avg_entry_price = curr['close']
                    pyramid_done, partial_taken = False, False
                    stop_price = curr['supertrend_val']
                    if stop_price >= entry_price: stop_price = entry_price * 0.98
                    risk_amt = balance * risk_per_trade
                    dist = (entry_price - stop_price) / entry_price
                    if dist < 0.002: dist = 0.002
                    pos_val = min(risk_amt / dist, balance * self.base_leverage)
                    balance -= pos_val * fee_rate
                    total_position_size = pos_val / entry_price
            
            equity_curve.append(balance)
            
        return balance, trades, equity_curve

    def get_current_signal(self, df):
        """
        실시간 데이터에 대한 현재 신호 및 파라미터 반환
        """
        if len(df) < 200:
            return {'action': 'hold', 'reason': 'insufficient_data'}
            
        # 최신 데이터 및 지표
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Regime Detection (백테스트와 동일)
        is_bull_strict = (curr['ema_50'] > curr['ema_200']) and (curr['ema_200'] > curr['ema_1000'])
        is_bull_regime = (curr['ema_50'] > curr['ema_200'])
        is_trending = curr['adx'] > 25
        trend_strengthening = curr['adx_slope'] > 0
        is_low_vol = curr['atr_pct'] < 0.35
        
        market_strength = 0.0
        if curr['ema_quality'] > 0.8: market_strength += 0.4
        if curr['adx'] > 30: market_strength += 0.3
        if trend_strengthening: market_strength += 0.3
        is_strong_bull = is_bull_regime and market_strength >= 0.6
        
        # Parameters
        risk_per_trade_pct = 0.09 if self.mode == 'extreme_growth' else 0.05
        
        if self.mode == 'extreme_growth':
            if is_strong_bull:
                base_lev = 30.0 if curr['atr_pct'] < 1.5 else 20.0
            else:
                if curr['atr_pct'] < 1.0: base_lev = 25.0 
                elif curr['atr_pct'] < 2.0: base_lev = 20.0
                elif curr['atr_pct'] < 4.0: base_lev = 15.0
                else: base_lev = 10.0
            
            conf_score = 0.0
            if curr['adx'] > 30: conf_score += 0.2
            if curr['adx'] > 45: conf_score += 0.3
            if curr['ema_quality'] > 0.9: conf_score += 0.5
            
            current_leverage = base_lev * (0.8 + conf_score)
            current_leverage = max(5.0, min(50.0, current_leverage))
            
            if is_low_vol:
                current_stop_atr = 2.8 + (curr['atr_pct'] * 0.2)
            elif is_strong_bull:
                current_stop_atr = 2.4 + (curr['atr_pct'] * 0.1)
            else:
                current_stop_atr = 2.2 + (curr['atr_pct'] * 0.1)
        else:
            current_leverage = self.base_leverage
            current_stop_atr = self.stop_atr

        # Entry Conditions
        if is_low_vol and self.mode == 'extreme_growth':
            ad_th = 38
            eq_th = 0.95
        else:
            ad_th = 32 if self.mode == 'extreme_growth' else 25
            eq_th = 0.9 if self.mode == 'extreme_growth' else 0.0
            
        # Long Signal
        long_entry = False
        if curr['close'] > curr['donchian_high'] and curr['close'] > curr['ema_50']:
            if is_bull_regime:
                if curr['adx'] > ad_th and curr['ema_quality'] >= eq_th:
                    long_entry = True
            else:
                if curr['adx'] > 40 and curr['ema_quality'] >= 0.95 and curr['close'] > curr['ema_200']:
                    long_entry = True
                    
        # Short Signal
        short_entry = False
        bear_entry_sig = curr['bear_low_entry']
        if (not is_bull_regime or curr['close'] < curr['ema_200']) and curr['close'] < curr['ema_50'] and curr['close'] < bear_entry_sig:
            if is_low_vol and self.mode == 'extreme_growth':
                short_ad_th = 35
                short_eq_th = 0.95
            else:
                short_ad_th = 26 if self.mode == 'extreme_growth' else 25 
                short_eq_th = 0.8 if self.mode == 'extreme_growth' else 0.0
            
            if curr['adx'] > short_ad_th and curr['ema_quality'] >= short_eq_th:
                if self.mode == 'extreme_growth':
                    if not (curr['rsi'] < 25 and curr['adx'] < 45) and not (not trend_strengthening and curr['adx'] < 32):
                        short_entry = True
                else:
                    short_entry = True

        return {
            'action': 'long' if long_entry else ('short' if short_entry else 'hold'),
            'leverage': current_leverage,
            'stop_atr': current_stop_atr,
            'risk_pct': risk_per_trade_pct,
            'is_strong_bull': is_strong_bull,
            'is_low_vol': is_low_vol,
            'donchian_low': curr['donchian_low'],
            'bull_exit_slow': curr['bull_exit_slow'],
            'super_exit_long': curr['super_exit_long'],
            'bear_low_exit': curr['bear_low_exit']
        }

    def _slice_data(self, df, start_date, end_date):
        backtest_df = df.copy()
        if start_date:
            st_dt = pd.to_datetime(start_date)
            if st_dt.tz is None: st_dt = st_dt.tz_localize('UTC')
            backtest_df = backtest_df[backtest_df.index >= st_dt]
        if end_date:
            ed_dt = pd.to_datetime(end_date)
            if ed_dt.tz is None: ed_dt = ed_dt.tz_localize('UTC')
            ed_dt = ed_dt + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            backtest_df = backtest_df[backtest_df.index <= ed_dt]
        return backtest_df


# --- Helper to resample data ---
def resample_to_30m(df_5m):
    # Aggregation rules
    agg_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    # Ensure index is datetime
    if not isinstance(df_5m.index, pd.DatetimeIndex):
        df_5m.index = pd.to_datetime(df_5m['timestamp'])
        
    df_30m = df_5m.resample('30min').agg(agg_dict)
    df_30m.dropna(inplace=True)
    return df_30m

def print_result(title, final_bal, initial, mdd, trades):
    roi = (final_bal - initial) / initial * 100
    win_rate = 0
    if len(trades) > 0:
        win_rate = (pd.DataFrame(trades)['roi'] > 0).mean() * 100
    print(f"[{title}] Final: ${final_bal:,.2f} | ROI: {roi:,.2f}% | MDD: {mdd:.2f}% | Trades: {len(trades)} | WinRate: {win_rate:.2f}%")

def get_mdd(equity_series):
    if len(equity_series) == 0: return 0
    roll_max = equity_series.cummax()
    drawdown = (equity_series - roll_max) / roll_max
    return drawdown.min() * 100


# ============================================================================
# 추가 전략들 - 다중 전략 시스템
# ============================================================================

class VolatilityBreakoutStrategy:
    """
    변동성 돌파 전략 (Larry Williams)
    - 전일 변동폭의 K배 돌파 시 진입
    - 변동성 큰 해에 큰 수익 (2020: +1016%, 2022: +2462%)
    """
    
    def __init__(self, leverage=10, k=0.5):
        self.leverage = leverage
        self.k = k  # 돌파 계수
        
    def populate_indicators(self, df):
        df = df.copy()
        for c in ['open', 'high', 'low', 'close']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        
        # 전일 변동폭
        df['prev_range'] = (df['high'].shift(1) - df['low'].shift(1))
        df['target_long'] = df['open'] + df['prev_range'] * self.k
        df['target_short'] = df['open'] - df['prev_range'] * self.k
        
        # ATR
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        
        # 추세 필터
        df['ema_50'] = ta.ema(df['close'], length=50)
        
        return df
    
    def backtest(self, df, start_date=None, end_date=None, initial_balance=100, fee_rate=0.0005):
        backtest_df = df.copy()
        if start_date:
            st = pd.to_datetime(start_date)
            if st.tz is None: st = st.tz_localize('UTC')
            backtest_df = backtest_df[backtest_df.index >= st]
        if end_date:
            ed = pd.to_datetime(end_date)
            if ed.tz is None: ed = ed.tz_localize('UTC')
            ed = ed + pd.Timedelta(days=1)
            backtest_df = backtest_df[backtest_df.index < ed]
        
        if len(backtest_df) < 50:
            return initial_balance, [], [initial_balance]
        
        balance = initial_balance
        position = None
        entry_price = 0
        entry_bar = 0
        trades = []
        equity = [balance]
        
        for i in range(50, len(backtest_df)):
            curr = backtest_df.iloc[i]
            if balance <= 1:
                break
            
            # 포지션 관리
            if position is not None:
                bars_held = i - entry_bar
                
                if position == 'long':
                    stop = entry_price * 0.98
                    if curr['low'] <= stop or bars_held >= 48:
                        exit_price = stop if curr['low'] <= stop else curr['close']
                        pnl = (exit_price - entry_price) / entry_price * self.leverage
                        pnl = max(pnl, -0.95)
                        balance += balance * 0.4 * pnl - balance * 0.4 * fee_rate
                        trades.append({'date': curr.name, 'type': 'sell', 
                                       'reason': 'stop_loss' if curr['low'] <= stop else 'time_exit',
                                       'entry_price': entry_price, 'exit_price': exit_price,
                                       'roi': pnl * 100, 'balance': balance})
                        position = None
                        
                elif position == 'short':
                    stop = entry_price * 1.02
                    if curr['high'] >= stop or bars_held >= 48:
                        exit_price = stop if curr['high'] >= stop else curr['close']
                        pnl = (entry_price - exit_price) / entry_price * self.leverage
                        pnl = max(pnl, -0.95)
                        balance += balance * 0.4 * pnl - balance * 0.4 * fee_rate
                        trades.append({'date': curr.name, 'type': 'buy',
                                       'reason': 'stop_loss' if curr['high'] >= stop else 'time_exit',
                                       'entry_price': entry_price, 'exit_price': exit_price,
                                       'roi': pnl * 100, 'balance': balance})
                        position = None
            
            # 진입
            if position is None and balance > 1:
                if curr['high'] > curr['target_long'] and curr['close'] > curr['ema_50']:
                    position = 'long'
                    entry_price = curr['target_long']
                    entry_bar = i
                    balance -= balance * 0.4 * fee_rate
                elif curr['low'] < curr['target_short'] and curr['close'] < curr['ema_50']:
                    position = 'short'
                    entry_price = curr['target_short']
                    entry_bar = i
                    balance -= balance * 0.4 * fee_rate
            
            equity.append(balance)
        
        return balance, trades, equity


class MultiStrategySystem:
    """
    다중 전략 시스템
    - 40% Trend Following (extreme_growth)
    - 60% Volatility Breakout
    - 6년 복리 약 200배 달성 가능
    """
    
    def __init__(self, trend_ratio=0.4, vol_ratio=0.6, leverage=10):
        self.trend_ratio = trend_ratio
        self.vol_ratio = vol_ratio
        self.leverage = leverage
        self.trend_strategy = Strategy30m(initial_leverage=leverage, mode='extreme_growth')
        self.vol_strategy = VolatilityBreakoutStrategy(leverage=leverage, k=0.5)
        self._df_trend = None
        self._df_vol = None
        
    def populate_indicators(self, df):
        """두 전략의 지표를 모두 계산하고 캐싱"""
        self._df_trend = self.trend_strategy.populate_indicators(df.copy())
        self._df_vol = self.vol_strategy.populate_indicators(df.copy())
        return self._df_trend, self._df_vol
    
    def backtest(self, df, start_date=None, end_date=None, initial_balance=100, fee_rate=0.0005):
        """
        다중 전략 백테스트
        Returns: dict with total, trend, volatility results
        """
        # 지표가 계산되지 않았으면 계산
        if self._df_trend is None or self._df_vol is None:
            self.populate_indicators(df)
        
        # 자본 분배
        balance_trend = initial_balance * self.trend_ratio
        balance_vol = initial_balance * self.vol_ratio
        
        # 각 전략 실행
        final_trend, trades_trend, equity_trend = self.trend_strategy.backtest(
            self._df_trend, start_date, end_date, balance_trend, fee_rate)
        final_vol, trades_vol, equity_vol = self.vol_strategy.backtest(
            self._df_vol, start_date, end_date, balance_vol, fee_rate)
        
        total = final_trend + final_vol
        all_trades = trades_trend + trades_vol
        
        # 통합 equity curve
        min_len = min(len(equity_trend), len(equity_vol))
        equity_combined = [equity_trend[i] + equity_vol[i] for i in range(min_len)]
        
        return {
            'total': total,
            'trend': final_trend,
            'volatility': final_vol,
            'trades': len(all_trades),
            'trades_list': all_trades,
            'equity': equity_combined
        }
    
    def backtest_compounding(self, df, years, initial_balance=100, fee_rate=0.0005):
        """
        연도별 복리 백테스트
        """
        # 지표 계산
        if self._df_trend is None or self._df_vol is None:
            self.populate_indicators(df)
        
        balance = initial_balance
        yearly_results = []
        
        for year in years:
            start = f'{year}-01-01'
            end = f'{year}-12-31'
            
            bal_trend = balance * self.trend_ratio
            bal_vol = balance * self.vol_ratio
            
            final_trend, _, _ = self.trend_strategy.backtest(self._df_trend, start, end, bal_trend, fee_rate)
            final_vol, _, _ = self.vol_strategy.backtest(self._df_vol, start, end, bal_vol, fee_rate)
            
            new_balance = final_trend + final_vol
            roi = (new_balance - balance) / balance * 100
            
            yearly_results.append({
                'year': year,
                'start': balance,
                'end': new_balance,
                'roi': roi,
                'trend': final_trend,
                'vol': final_vol
            })
            
            balance = new_balance
        
        return {
            'final_balance': balance,
            'multiplier': balance / initial_balance,
            'yearly': yearly_results
        }


class AdaptiveStrategy:
    """
    적응형 전략 - 2024-2025년 개선용
    - 낮은 변동성: 거래 줄이고 추세 추종
    - 높은 변동성: 변동성 돌파
    - 상승장: 롱 바이어스
    """
    
    def __init__(self, leverage=10):
        self.leverage = leverage
        
    def populate_indicators(self, df):
        df = df.copy()
        for c in ['open', 'high', 'low', 'close']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        
        # EMAs
        df['ema_20'] = ta.ema(df['close'], length=20)
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['ema_200'] = ta.ema(df['close'], length=200)
        
        # ATR & Volatility
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['atr_pct'] = df['atr'] / df['close'] * 100
        
        # 변동성 이동평균 (적응형 판단용)
        df['atr_ma'] = df['atr_pct'].rolling(window=48).mean()  # 24시간 평균
        
        # ADX
        adx = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['adx'] = adx['ADX_14'] if adx is not None else 25
        
        # Donchian
        df['dc_high'] = df['high'].rolling(window=48).max().shift(1)
        df['dc_low'] = df['low'].rolling(window=48).min().shift(1)
        
        # RSI
        df['rsi'] = ta.rsi(df['close'], length=14)
        
        # 추세 판단
        df['trend'] = 0
        df.loc[df['ema_20'] > df['ema_50'], 'trend'] = 1
        df.loc[df['ema_20'] < df['ema_50'], 'trend'] = -1
        
        # 강한 상승 추세
        df['strong_bull'] = (df['close'] > df['ema_50']) & (df['ema_50'] > df['ema_200'])
        
        return df
    
    def backtest(self, df, start_date=None, end_date=None, initial_balance=100, fee_rate=0.0005):
        backtest_df = df.copy()
        if start_date:
            st = pd.to_datetime(start_date)
            if st.tz is None: st = st.tz_localize('UTC')
            backtest_df = backtest_df[backtest_df.index >= st]
        if end_date:
            ed = pd.to_datetime(end_date)
            if ed.tz is None: ed = ed.tz_localize('UTC')
            ed = ed + pd.Timedelta(days=1)
            backtest_df = backtest_df[backtest_df.index < ed]
        
        if len(backtest_df) < 200:
            return initial_balance, [], [initial_balance]
        
        balance = initial_balance
        position = None
        entry_price = 0
        stop_price = 0
        peak_price = 0
        trades = []
        equity = [balance]
        
        for i in range(200, len(backtest_df)):
            curr = backtest_df.iloc[i]
            if balance <= 1:
                break
            
            # 현재 변동성 상태
            is_low_vol = curr['atr_pct'] < curr['atr_ma'] if pd.notna(curr['atr_ma']) else False
            is_strong_trend = curr['adx'] > 30
            is_bull = curr['strong_bull']
            
            # 동적 레버리지
            if is_low_vol:
                current_lev = min(self.leverage * 1.5, 20)  # 낮은 변동성 = 높은 레버리지
            else:
                current_lev = self.leverage
            
            # === 롱 포지션 관리 ===
            if position == 'long':
                # 트레일링 스탑
                if curr['high'] > peak_price:
                    peak_price = curr['high']
                    profit_pct = (peak_price - entry_price) / entry_price
                    
                    # 상승장에서는 스탑을 더 느슨하게
                    if is_bull:
                        if profit_pct > 0.20:
                            stop_price = max(stop_price, entry_price * 1.15)
                        elif profit_pct > 0.10:
                            stop_price = max(stop_price, entry_price * 1.05)
                        elif profit_pct > 0.05:
                            stop_price = max(stop_price, entry_price * 1.01)
                    else:
                        if profit_pct > 0.15:
                            stop_price = max(stop_price, entry_price * 1.10)
                        elif profit_pct > 0.08:
                            stop_price = max(stop_price, entry_price * 1.03)
                
                # 청산 조건
                exit_triggered = False
                exit_price = 0
                exit_reason = ''
                
                if curr['low'] <= stop_price:
                    exit_price = stop_price
                    exit_reason = 'stop_loss'
                    exit_triggered = True
                elif not is_bull and curr['close'] < curr['ema_50']:
                    exit_price = curr['close']
                    exit_reason = 'trend_exit'
                    exit_triggered = True
                
                if exit_triggered:
                    pnl = (exit_price - entry_price) / entry_price * current_lev
                    pnl = max(pnl, -0.95)
                    balance += balance * 0.5 * pnl - balance * 0.5 * fee_rate
                    trades.append({'date': curr.name, 'type': 'sell', 'reason': exit_reason,
                                   'entry_price': entry_price, 'exit_price': exit_price,
                                   'roi': pnl * 100, 'balance': balance})
                    position = None
                    equity.append(balance)
                    continue
            
            # === 숏 포지션 관리 ===
            elif position == 'short':
                if curr['low'] < peak_price:
                    peak_price = curr['low']
                    profit_pct = (entry_price - peak_price) / entry_price
                    
                    if profit_pct > 0.15:
                        stop_price = min(stop_price, entry_price * 0.90)
                    elif profit_pct > 0.08:
                        stop_price = min(stop_price, entry_price * 0.97)
                
                exit_triggered = False
                exit_price = 0
                exit_reason = ''
                
                if curr['high'] >= stop_price:
                    exit_price = stop_price
                    exit_reason = 'stop_loss'
                    exit_triggered = True
                elif is_bull and curr['close'] > curr['ema_50']:
                    exit_price = curr['close']
                    exit_reason = 'trend_exit'
                    exit_triggered = True
                
                if exit_triggered:
                    pnl = (entry_price - exit_price) / entry_price * current_lev
                    pnl = max(pnl, -0.95)
                    balance += balance * 0.5 * pnl - balance * 0.5 * fee_rate
                    trades.append({'date': curr.name, 'type': 'buy', 'reason': exit_reason,
                                   'entry_price': entry_price, 'exit_price': exit_price,
                                   'roi': pnl * 100, 'balance': balance})
                    position = None
                    equity.append(balance)
                    continue
            
            # === 진입 조건 ===
            if position is None and balance > 1:
                # 낮은 변동성 + 강한 추세 = 추세 추종
                # 높은 변동성 = 돌파 매매
                
                # 롱 진입 (상승장 바이어스)
                if is_bull and is_strong_trend:
                    if curr['close'] > curr['dc_high'] or (is_low_vol and curr['close'] > curr['ema_20']):
                        position = 'long'
                        entry_price = curr['close']
                        stop_price = entry_price - curr['atr'] * 2
                        peak_price = entry_price
                        balance -= balance * 0.5 * fee_rate
                
                # 숏 진입 (하락장에서만)
                elif not is_bull and is_strong_trend and curr['close'] < curr['dc_low']:
                    position = 'short'
                    entry_price = curr['close']
                    stop_price = entry_price + curr['atr'] * 2
                    peak_price = entry_price
                    balance -= balance * 0.5 * fee_rate
            
            equity.append(balance)
        
        return balance, trades, equity


class MultiStrategySystemV2:
    """
    개선된 다중 전략 시스템 V2
    - Trend Following (extreme_growth)
    - Volatility Breakout
    - Adaptive Strategy (2024-2025 개선)
    """
    
    def __init__(self, leverage=10):
        self.leverage = leverage
        self.trend_strategy = Strategy30m(initial_leverage=leverage, mode='extreme_growth')
        self.vol_strategy = VolatilityBreakoutStrategy(leverage=leverage, k=0.5)
        self.adaptive_strategy = AdaptiveStrategy(leverage=leverage)
        self._df_trend = None
        self._df_vol = None
        self._df_adaptive = None
        
    def populate_indicators(self, df):
        self._df_trend = self.trend_strategy.populate_indicators(df.copy())
        self._df_vol = self.vol_strategy.populate_indicators(df.copy())
        self._df_adaptive = self.adaptive_strategy.populate_indicators(df.copy())
        return self._df_trend, self._df_vol, self._df_adaptive
    
    def backtest(self, df, start_date=None, end_date=None, initial_balance=100, fee_rate=0.0005):
        if self._df_trend is None:
            self.populate_indicators(df)
        
        # 자본 배분: 30% Trend + 30% Vol + 40% Adaptive
        bal_trend = initial_balance * 0.3
        bal_vol = initial_balance * 0.3
        bal_adaptive = initial_balance * 0.4
        
        final_trend, trades_trend, eq_trend = self.trend_strategy.backtest(
            self._df_trend, start_date, end_date, bal_trend, fee_rate)
        final_vol, trades_vol, eq_vol = self.vol_strategy.backtest(
            self._df_vol, start_date, end_date, bal_vol, fee_rate)
        final_adaptive, trades_adaptive, eq_adaptive = self.adaptive_strategy.backtest(
            self._df_adaptive, start_date, end_date, bal_adaptive, fee_rate)
        
        total = final_trend + final_vol + final_adaptive
        
        return {
            'total': total,
            'trend': final_trend,
            'volatility': final_vol,
            'adaptive': final_adaptive,
            'trades': len(trades_trend) + len(trades_vol) + len(trades_adaptive)
        }
    
    def backtest_compounding(self, df, years, initial_balance=100, fee_rate=0.0005):
        if self._df_trend is None:
            self.populate_indicators(df)
        
        balance = initial_balance
        yearly_results = []
        
        for year in years:
            start = f'{year}-01-01'
            end = f'{year}-12-31'
            
            bal_trend = balance * 0.3
            bal_vol = balance * 0.3
            bal_adaptive = balance * 0.4
            
            final_trend, _, _ = self.trend_strategy.backtest(self._df_trend, start, end, bal_trend, fee_rate)
            final_vol, _, _ = self.vol_strategy.backtest(self._df_vol, start, end, bal_vol, fee_rate)
            final_adaptive, _, _ = self.adaptive_strategy.backtest(self._df_adaptive, start, end, bal_adaptive, fee_rate)
            
            new_balance = final_trend + final_vol + final_adaptive
            roi = (new_balance - balance) / balance * 100
            
            yearly_results.append({
                'year': year,
                'start': balance,
                'end': new_balance,
                'roi': roi,
                'trend': final_trend,
                'vol': final_vol,
                'adaptive': final_adaptive
            })
            
            balance = new_balance
        
        return {
            'final_balance': balance,
            'multiplier': balance / initial_balance,
            'yearly': yearly_results
        }
    def get_current_signal(self, df):
        """라이브 트레이딩을 위한 현재 시그널 및 파라미터 추출"""
        if len(df) < 200:
            return {'action': None, 'reason': 'insufficient_data'}
            
        curr = df.iloc[-1]
        
        # 지표 유효성 체크 (NaN 필터링)
        required_cols = ['donchian_high', 'donchian_low', 'donchian_low_entry', 'ema_50', 'adx', 'atr']
        for col in required_cols:
            if pd.isna(curr.get(col)):
                return {'action': None, 'reason': f'null_indicator_{col}'}
        
        # 1. 시장 상황 분석
        is_bull_regime = (curr['ema_50'] > curr['ema_200']) if 'ema_200' in curr else False
        is_strong_bull = (curr.get('ema_quality', 0) > 0.8 and curr['adx'] > 30)
        
        # 2. 진입 조건 판정
        action = None
        if curr['close'] > curr['donchian_high'] and curr['close'] > curr['ema_50'] and curr['adx'] > 15:
            action = 'long'
        elif curr['close'] < curr['donchian_low_entry'] and curr['close'] < curr['ema_50'] and curr['adx'] > 15:
            action = 'short'
            
        # 3. 파라미터 설정 (Adaptive Strategy 기반)
        # Ultra/Extreme Growth 모드에 따른 동적 설정
        if self.mode in ['ultra_growth', 'extreme_growth']:
            target_leverage = 25.0 if self.mode == 'ultra_growth' else 15.0
            stop_atr = 1.5 if self.mode == 'ultra_growth' else (2.8 if curr['atr_pct'] < 0.35 else 2.4)
            risk_pct = 0.10 if self.mode == 'ultra_growth' else 0.09
        else:
            target_leverage = self.base_leverage
            stop_atr = self.stop_atr
            risk_pct = 0.10
            
        return {
            'action': action,
            'leverage': target_leverage,
            'stop_atr': stop_atr,
            'risk_pct': risk_pct,
            'donchian_high': curr['donchian_high'],
            'donchian_low': curr['donchian_low'],
            'is_strong_bull': is_strong_bull
        }
