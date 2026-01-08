"""
자동 재학습 스크립트 (Auto Retrainer)
매일 실행되어 최신 데이터로 모델을 업데이트합니다.
"""
import ccxt
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def fetch_and_train():
    try:
        print(f"[{datetime.now()}] 🔄 재학습 시작...")
        
        # 1. 최신 데이터 수집 (Binance)
        api_key = os.getenv('BINANCE_API_KEY')
        secret = os.getenv('BINANCE_SECRET')
        exchange = ccxt.binance({
            'apiKey': api_key, 
            'secret': secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        # 최근 100일치 15분봉 데이터 (약 9600개) - 충분함
        ohlcv = exchange.fetch_ohlcv('BTC/USDT', '15m', limit=1000) 
        # 더 많은 데이터가 필요하면 반복 호출해야 함. 여기서는 간략히 1000개로 예시.
        # 실제 성능 유지를 위해선 최소 1년치가 좋으므로, 기존 csv가 있다면 병합하거나 fetch_ohlcv를 반복해야 함.
        # 여기서는 기존 5년치 csv가 있다고 가정하고, 없으면 새로 받음.
        
        # 데이터 로드 전략:
        # 1. 기존 'latest_data.csv'가 있으면 로드
        # 2. 거래소에서 최근 데이터 가져와서 병합
        # 3. 저장 및 학습
        
        csv_path = 'latest_data_15m.csv'
        if os.path.exists(csv_path):
            df_old = pd.read_csv(csv_path)
            if 'datetime' not in df_old.columns:
                 df_old['datetime'] = pd.to_datetime(df_old['timestamp'], unit='ms')
            else:
                 df_old['datetime'] = pd.to_datetime(df_old['datetime'])
            last_time = df_old['datetime'].max()
            since = int(last_time.timestamp() * 1000)
            print(f"   기존 데이터 로드 완료 ({len(df_old)}건)")
        else:
            df_old = pd.DataFrame()
            since = exchange.parse8601('2024-01-01T00:00:00Z') # 없으면 1년 전부터
            print("   기존 데이터 없음, 새로 다운로드...")

        # 최신 데이터 Fetch Loop
        all_ohlcv = []
        while True:
            ohlcv = exchange.fetch_ohlcv('BTC/USDT', '15m', since=since, limit=1000)
            if not ohlcv: break
            last_timestamp = ohlcv[-1][0]
            if last_timestamp == since: break
            since = last_timestamp + 1
            all_ohlcv.extend(ohlcv)
            print(f"   다운로드 중... {len(all_ohlcv)}건 추가")
            if len(ohlcv) < 1000: break
            
        if all_ohlcv:
            df_new = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_new['datetime'] = pd.to_datetime(df_new['timestamp'], unit='ms')
            
            if not df_old.empty:
                df = pd.concat([df_old, df_new]).drop_duplicates(subset='timestamp').reset_index(drop=True)
            else:
                df = df_new
        else:
            df = df_old
            
        df.to_csv(csv_path, index=False)
        print(f"   데이터 병합 완료: 총 {len(df)}건")
        
        # 2. 전처리 및 학습
        train_models(df)
        
    except Exception as e:
        print(f"❌ 재학습 실패: {e}")

def train_models(df):
    # 전처리 (Strategy와 동일)
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
    
    df['future_return'] = df['close'].shift(-4) / df['close'] - 1
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    
    feature_cols = [
        'rsi', 'rsi_change', 'dist_ema20', 'dist_ema60', 'dist_ema200', 
        'atr', 'vol_change', 'macd_hist', 'macd_hist_change', 'stoch_k', 'bb_width'
    ]
    
    # Train Logic
    def create_data(target_type):
        df_t = df.copy()
        if target_type == 'short':
            df_t['signal'] = (df_t['close'] < df_t['ema_60'])
            df_t['target'] = (df_t['future_return'] < -0.003).astype(int)
            data = df_t[df_t['signal']]
            return data[feature_cols], data['target']
        elif target_type == 'long':
            df_t['signal'] = (df_t['close'] > df_t['ema_60'])
            df_t['target'] = (df_t['future_return'] > 0.003).astype(int)
            data = df_t[df_t['signal']]
            return data[feature_cols], data['target']
        elif target_type == 'regime':
            df_t['target'] = 0
            df_t.loc[(df_t['close'] > df_t['ema_200']) & (df_t['ema_20'] > df_t['ema_60']), 'target'] = 1
            df_t.loc[(df_t['close'] < df_t['ema_200']) & (df_t['ema_20'] < df_t['ema_60']), 'target'] = 2
            return df_t[feature_cols], df_t['target']

    print("🚀 모델 훈련 시작...")
    X_s, y_s = create_data('short')
    model_s = xgb.XGBClassifier(n_estimators=100, max_depth=6, learning_rate=0.05, random_state=42)
    model_s.fit(X_s, y_s)
    joblib.dump({'model': model_s, 'features': feature_cols}, 'lgbm_short.pkl')
    
    X_l, y_l = create_data('long')
    model_l = xgb.XGBClassifier(n_estimators=100, max_depth=6, learning_rate=0.05, random_state=42)
    model_l.fit(X_l, y_l)
    joblib.dump({'model': model_l, 'features': feature_cols}, 'lgbm_long.pkl')
    
    X_r, y_r = create_data('regime')
    model_r = xgb.XGBClassifier(n_estimators=100, max_depth=6, learning_rate=0.05, num_class=3, objective='multi:softmax', random_state=42)
    model_r.fit(X_r, y_r)
    joblib.dump({'model': model_r, 'features': feature_cols}, 'lgbm_regime.pkl')
    
    print(f"✅ 모델 업데이트 완료: {datetime.now()}")

if __name__ == "__main__":
    fetch_and_train()
