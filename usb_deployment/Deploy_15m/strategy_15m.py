import joblib
import pandas as pd
import numpy as np
import logging
import os

class Strategy:
    def __init__(self, config):
        self.config = config
        self.load_models()
        self.regime_settings = {
            0: {'name': 'SIDEWAYS', 'action': 'skip'},
            1: {'name': 'BULL', 'action': 'long', 'risk': 0.04, 'leverage': 12},
            2: {'name': 'BEAR', 'action': 'short', 'risk': 0.03, 'leverage': 8}
        }

    def load_models(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.short_model_data = joblib.load(os.path.join(base_dir, 'lgbm_short.pkl'))
            self.long_model_data = joblib.load(os.path.join(base_dir, 'lgbm_long.pkl'))
            self.regime_model_data = joblib.load(os.path.join(base_dir, 'lgbm_regime.pkl'))
            
            self.short_model = self.short_model_data['model']
            self.long_model = self.long_model_data['model']
            self.regime_model = self.regime_model_data['model']
            logging.info("Multi-Models Loaded Successfully (XGBoost)")
        except Exception as e:
            logging.error(f"Failed to load models: {e}")
            self.short_model = None

    def get_features(self, row, feature_list):
        features = {}
        for f in feature_list:
            val = row.get(f, 0)
            if pd.isna(val) or val == np.inf or val == -np.inf:
                val = 0
            features[f] = val
        return pd.DataFrame([features])

    def prepare_features(self, df):
        # 모델이 필요로 하는 피처 생성 (훈련 시와 동일하게)
        df = df.copy()
        
        # EMA
        df['ema_20'] = df['close'].ewm(span=20).mean()
        df['ema_60'] = df['close'].ewm(span=60).mean()
        df['ema_200'] = df['close'].ewm(span=200).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp12 - exp26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # Stochastic RSI
        min_val = df['rsi'].rolling(window=14).min()
        max_val = df['rsi'].rolling(window=14).max()
        df['stoch_k'] = (df['rsi'] - min_val) / (max_val - min_val) * 100
        
        # ATR
        high = df['high']
        low = df['low']
        close = df['close']
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        
        # Bollinger Bands Width
        std = df['close'].rolling(20).std()
        df['bb_upper'] = df['ema_20'] + (std * 2)
        df['bb_lower'] = df['ema_20'] - (std * 2)
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['ema_20']
        
        # Derived Features
        df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
        df['dist_ema60'] = (df['close'] - df['ema_60']) / df['ema_60']
        df['dist_ema200'] = (df['close'] - df['ema_200']) / df['ema_200']
        df['rsi_change'] = df['rsi'].diff()
        df['vol_change'] = df['volume'].pct_change()
        df['macd_hist_change'] = df['macd_hist'].diff()
        
        return df

    def check_entry(self, df):
        if self.short_model is None or len(df) < 200:
            return None
            
        df = self.prepare_features(df)
        current = df.iloc[-1]
        
        # 1. Regime Detection
        regime = 0
        try:
            feats = self.get_features(current, self.regime_model_data['features'])
            regime = int(self.regime_model.predict(feats)[0])
        except:
            pass
            
        settings = self.regime_settings.get(regime, {'action': 'skip'})
        action = settings['action']
        
        if action == 'skip':
            return None
            
        # 2. Signal Prediction
        signal = None
        threshold = 0.55
        
        if action == 'long':
            feats = self.get_features(current, self.long_model_data['features'])
            prob = self.long_model.predict_proba(feats)[0][1]
            if prob > threshold:
                signal = 'LONG'
                logging.info(f"Regime: BULL | Long Prob: {prob:.2%}")
                
        elif action == 'short':
            feats = self.get_features(current, self.short_model_data['features'])
            prob = self.short_model.predict_proba(feats)[0][1]
            if prob > threshold:
                signal = 'SHORT'
                logging.info(f"Regime: BEAR | Short Prob: {prob:.2%}")
                
        return signal

    def calculate_stops(self, df, signal, price):
        atr = df.iloc[-1].get('atr', price * 0.01)
        if pd.isna(atr): atr = price * 0.01
        
        sl_mult = 1.0
        tp_mult = 3.0
        
        if signal == 'LONG':
            sl = price - (atr * sl_mult)
            tp = price + (atr * tp_mult)
        else:
            sl = price + (atr * sl_mult)
            tp = price - (atr * tp_mult)
            
        return sl, tp
