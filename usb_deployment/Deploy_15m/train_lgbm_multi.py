"""
다중 LightGBM 모델 훈련 (15분봉)
1. Short 전용 모델
2. Long 전용 모델
3. 시장 레짐 분류 모델
"""
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import lightgbm as lgb
import joblib
import os
from strategy import add_indicators

def load_and_prepare_data(data_path='btc_usdt_5m_5y.csv'):
    print(f"📊 데이터 로딩: {data_path}")
    df = pd.read_csv(data_path)
    
    if 'datetime' not in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    else:
        df['datetime'] = pd.to_datetime(df['datetime'])
    
    # 15분봉으로 리샘플링
    print("⏱️ 15분봉으로 리샘플링...")
    df.set_index('datetime', inplace=True)
    df_15m = df.resample('15min').agg({
        'open': 'first', 'high': 'max', 'low': 'min',
        'close': 'last', 'volume': 'sum'
    }).dropna().reset_index()
    
    # 지표 추가 (기존 strategy.py 활용하되, 필요한 지표가 없으면 추가 계산)
    try:
        df_15m = add_indicators(df_15m)
    except:
        # strategy.py가 기존 것과 다를 경우 기본적인것 직접 계산
        print("⚠️ 기본 지표 직접 계산")
        df_15m['ema_20'] = df_15m['close'].ewm(span=20).mean()
        df_15m['ema_60'] = df_15m['close'].ewm(span=60).mean()
        df_15m['ema_200'] = df_15m['close'].ewm(span=200).mean()
        
        # RSI
        delta = df_15m['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_15m['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR
        high = df_15m['high']
        low = df_15m['low']
        close = df_15m['close']
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df_15m['atr'] = tr.rolling(14).mean()

        # ADX (약식)
        df_15m['adx'] = 25  # 기본값
    
    # 추가 피처
    df_15m['dist_ema20'] = (df_15m['close'] - df_15m['ema_20']) / df_15m['ema_20']
    df_15m['dist_ema60'] = (df_15m['close'] - df_15m['ema_60']) / df_15m['ema_60']
    df_15m['dist_ema200'] = (df_15m['close'] - df_15m['ema_200']) / df_15m['ema_200']
    df_15m['rsi_change'] = df_15m['rsi'].diff()
    df_15m['vol_change'] = df_15m['volume'].pct_change()
    df_15m['bb_width'] = 0 # 간소화
    
    # 미래 타겟 (15분 * 4 = 1시간 후)
    df_15m['future_return'] = df_15m['close'].shift(-4) / df_15m['close'] - 1
    
    print(f"📈 총 캔들: {len(df_15m):,}개")
    return df_15m

def create_training_data(df, target_type):
    feature_cols = [
        'rsi', 'rsi_change', 'dist_ema20', 'dist_ema60', 'dist_ema200', 
        'atr', 'vol_change'
    ]
    
    df = df.copy().dropna()
    
    if target_type == 'short':
        # Short 신호 조건 (약한 하락세)
        df['signal'] = (df['close'] < df['ema_60']) & (df['rsi'] > 50)
        # 성공: 1시간 후 하락
        df['target'] = (df['future_return'] < -0.005).astype(int)
        
    elif target_type == 'long':
        # Long 신호 조건 (약한 상승세)
        df['signal'] = (df['close'] > df['ema_60']) & (df['rsi'] < 50)
        # 성공: 1시간 후 상승
        df['target'] = (df['future_return'] > 0.005).astype(int)
        
    elif target_type == 'regime':
        # 0: SIDE, 1: BULL, 2: BEAR
        df['target'] = 0
        
        # BULL
        bull_mask = (df['close'] > df['ema_200']) & (df['ema_20'] > df['ema_60'])
        df.loc[bull_mask, 'target'] = 1
        
        # BEAR
        bear_mask = (df['close'] < df['ema_200']) & (df['ema_20'] < df['ema_60'])
        df.loc[bear_mask, 'target'] = 2
        
        return df[feature_cols], df['target'], feature_cols

    # 신호가 있는 데이터만 필터링 (Long/Short 경우)
    data = df[df['signal']].copy()
    return data[feature_cols], data['target'], feature_cols

def train_lgbm(X, y, name, num_class=1):
    print(f"\n🚀 {name} 모델 훈련...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    if num_class > 1:
        model = lgb.LGBMClassifier(
            n_estimators=200, learning_rate=0.05, num_leaves=31,
            objective='multiclass', num_class=num_class, random_state=42
        )
    else:
        model = lgb.LGBMClassifier(
            n_estimators=200, learning_rate=0.05, num_leaves=31,
            objective='binary', random_state=42
        )
        
    model.fit(X_train, y_train)
    score = model.score(X_test, y_test)
    print(f"   정확도: {score*100:.1f}%")
    return model, score

def main():
    df = load_and_prepare_data()
    
    # 1. Short Model
    X_s, y_s, feats_s = create_training_data(df, 'short')
    model_s, score_s = train_lgbm(X_s, y_s, "Short")
    
    # 2. Long Model
    X_l, y_l, feats_l = create_training_data(df, 'long')
    model_l, score_l = train_lgbm(X_l, y_l, "Long")
    
    # 3. Regime Model
    X_r, y_r, feats_r = create_training_data(df, 'regime')
    model_r, score_r = train_lgbm(X_r, y_r, "Regime", num_class=3)
    
    # 저장
    print("\n💾 모델 저장...")
    joblib.dump({'model': model_s, 'features': feats_s, 'acc': score_s}, 'lgbm_short.pkl')
    joblib.dump({'model': model_l, 'features': feats_l, 'acc': score_l}, 'lgbm_long.pkl')
    joblib.dump({'model': model_r, 'features': feats_r, 'acc': score_r}, 'lgbm_regime.pkl')
    print("✅ 완료")

if __name__ == "__main__":
    main()
