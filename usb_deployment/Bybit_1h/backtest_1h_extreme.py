"""
1시간봉 극한의 수익 테스트 (Madness Mode)
"""
import pandas as pd
import numpy as np
import joblib
import os
import time

class ExtremeBacktester:
    def __init__(self, data_path='btc_usdt_5m_5y.csv'):
        self.data_path = data_path
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        try:
            self.short_model = joblib.load(os.path.join(base_dir, 'xgb_short_1h.pkl'))['model']
            self.long_model = joblib.load(os.path.join(base_dir, 'xgb_long_1h.pkl'))['model']
            self.regime_model = joblib.load(os.path.join(base_dir, 'xgb_regime_1h.pkl'))['model']
            self.short_feats = joblib.load(os.path.join(base_dir, 'xgb_short_1h.pkl'))['features']
            self.long_feats = joblib.load(os.path.join(base_dir, 'xgb_long_1h.pkl'))['features']
            self.regime_feats = joblib.load(os.path.join(base_dir, 'xgb_regime_1h.pkl'))['features']
        except: return

        self.taker_fee = 0.0004
        self.slippage = 0.0003
        self.load_data()
    
    def load_data(self):
        print("📊 데이터 로딩...")
        df = pd.read_csv(self.data_path)
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('datetime', inplace=True)
        df_1h = df.resample('1h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna().reset_index()
        
        # 지표 (벡터화)
        df = df_1h
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
        
        df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
        df['dist_ema60'] = (df['close'] - df['ema_60']) / df['ema_60']
        df['dist_ema200'] = (df['close'] - df['ema_200']) / df['ema_200']
        df['rsi_change'] = df['rsi'].diff()
        df['vol_change'] = df['volume'].pct_change()
        df['macd_hist_change'] = df['macd_hist'].diff()
        
        all_feats = list(set(self.short_feats + self.long_feats + self.regime_feats))
        for f in all_feats:
            if f not in df.columns: df[f] = 0
            df[f] = df[f].fillna(0).replace([np.inf, -np.inf], 0)
            
        print("🚀 고속 예측 중...")
        df['regime'] = self.regime_model.predict(df[self.regime_feats])
        df['long_prob'] = self.long_model.predict_proba(df[self.long_feats])[:, 1]
        df['short_prob'] = self.short_model.predict_proba(df[self.short_feats])[:, 1]
        self.df = df

    def run(self):
        print("\n🔥 MADNESS MODE TEST (Leverage 50x, Risk 20%)")
        
        REGIME_CONFIG = {
            1: {'action': 'long', 'risk': 0.20, 'leverage': 50}, # 미친 설정
            2: {'action': 'short', 'risk': 0.15, 'leverage': 30}
        }
        
        ts_activation = 1.0 # 1 ATR 수익 시 바로 발동
        ts_callback = 0.5   # 0.5 ATR 하락 시 즉시 청산 (스캘핑 수준)
        
        balance = 100000
        data = self.df.to_dict('records')
        
        position = 0
        entry_price = 0
        sl_price = 0
        max_price = 0
        min_price = 0
        
        max_balance = balance
        max_dd = 0
        
        print(f"초기 잔고: {balance:,.0f}원")
        
        for i, row in enumerate(data):
            if i < 200: continue
            if balance < 1000: break # 파산
            
            price = row['close']
            atr = row['atr']
            if atr <= 0: continue
            
            # Drawdown check
            if balance > max_balance: max_balance = balance
            dd = (max_balance - balance) / max_balance
            if dd > max_dd: max_dd = dd
            
            # Position Management
            if position != 0:
                is_long = position > 0
                exit_price = None
                
                # TS
                if is_long:
                    if row['high'] > max_price:
                        max_price = row['high']
                        if max_price > entry_price + (atr * ts_activation):
                            new_sl = max_price - (atr * ts_callback)
                            if new_sl > sl_price: sl_price = new_sl
                    if row['low'] <= sl_price: exit_price = sl_price * (1 - self.slippage)
                else:
                    if row['low'] < min_price:
                        min_price = row['low']
                        if min_price < entry_price - (atr * ts_activation):
                            new_sl = min_price + (atr * ts_callback)
                            if new_sl < sl_price: sl_price = new_sl
                    if row['high'] >= sl_price: exit_price = sl_price * (1 + self.slippage)
                    
                if exit_price:
                    if is_long: pnl = (exit_price - entry_price) * position
                    else: pnl = (entry_price - exit_price) * abs(position)
                    fee = abs(position) * exit_price * self.taker_fee
                    balance += (pnl - fee)
                    position = 0
            
            # Ensure liquidiy check (simplified)
            
            # Entry
            if position == 0:
                regime = int(row['regime'])
                cfg = REGIME_CONFIG.get(regime, {})
                if not cfg: continue
                
                action = cfg['action']
                threshold = 0.52
                
                signal = None
                if action == 'long' and row['long_prob'] > threshold: signal = 'long'
                elif action == 'short' and row['short_prob'] > threshold: signal = 'short'
                
                if signal:
                    lev = cfg['leverage']
                    risk = cfg['risk']
                    sl_dist = atr
                    if sl_dist == 0: continue
                    
                    risk_amt = balance * risk
                    pos_val = min(risk_amt / (sl_dist/price), balance * lev)
                    if pos_val < 10000: continue # 최소 주문 금액

                    fee = pos_val * self.taker_fee
                    balance -= fee
                    qty = (pos_val - fee) / price
                    
                    position = qty if signal == 'long' else -qty
                    entry_price = price
                    
                    if signal == 'long':
                        sl_price = price - atr
                        max_price = price
                    else:
                        sl_price = price + atr
                        min_price = price

        print(f"최종 잔고: {balance:,.0f}원")
        print(f"수익률: {(balance-100000)/100000*100:,.0f}%")
        print(f"MDD: {max_dd*100:.1f}%")

ExtremeBacktester().run()
