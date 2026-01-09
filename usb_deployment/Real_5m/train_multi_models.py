"""
다중 ML 모델 훈련
1. Short 전용 모델 (하락장 수익)
2. Long 전용 모델 (상승장 수익)
3. 시장 레짐 분류 모델
"""
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import xgboost as xgb
import joblib
import os
from strategy import add_indicators

def load_and_prepare_data(data_path='data/btc_usdt_5m_5y.csv'):
    """데이터 로드 및 전처리"""
    print(f"📊 데이터 로딩: {data_path}")
    df = pd.read_csv(data_path)
    
    if 'datetime' not in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    else:
        df['datetime'] = pd.to_datetime(df['datetime'])
    
    # 1시간봉으로 리샘플링
    print("⏱️ 1시간봉으로 리샘플링...")
    df.set_index('datetime', inplace=True)
    df_1h = df.resample('1h').agg({
        'open': 'first', 'high': 'max', 'low': 'min',
        'close': 'last', 'volume': 'sum'
    }).dropna().reset_index()
    
    # 지표 추가
    df_1h = add_indicators(df_1h)
    
    # 추가 피처
    df_1h['dist_ema20'] = (df_1h['close'] - df_1h['ema_20']) / df_1h['ema_20']
    df_1h['dist_ema60'] = (df_1h['close'] - df_1h['ema_60']) / df_1h['ema_60']
    df_1h['rsi_change'] = df_1h['rsi'].diff()
    df_1h['adx_change'] = df_1h['adx'].diff()
    df_1h['vol_change'] = df_1h['volume'].pct_change()
    df_1h['stoch_diff'] = df_1h['stoch_k'] - df_1h['stoch_d']
    df_1h['bb_width'] = (df_1h['bb_upper'] - df_1h['bb_lower']) / df_1h['bb_middle']
    df_1h['vol_ratio'] = df_1h['volume'] / df_1h['vol_ma20']
    df_1h['ema_slope'] = df_1h['ema_20'].pct_change() * 100
    
    # 200 EMA
    df_1h['ema_200'] = df_1h['close'].ewm(span=200).mean()
    df_1h['dist_ema200'] = (df_1h['close'] - df_1h['ema_200']) / df_1h['ema_200']
    
    # 미래 가격 변화 (타겟)
    df_1h['future_return_4h'] = df_1h['close'].shift(-4) / df_1h['close'] - 1
    df_1h['future_return_8h'] = df_1h['close'].shift(-8) / df_1h['close'] - 1
    df_1h['future_return_24h'] = df_1h['close'].shift(-24) / df_1h['close'] - 1
    
    # 미래 고점/저점 (SL/TP 체크용)
    df_1h['future_high_4h'] = df_1h['high'].rolling(4).max().shift(-4)
    df_1h['future_low_4h'] = df_1h['low'].rolling(4).min().shift(-4)
    
    print(f"📈 총 캔들: {len(df_1h):,}개")
    return df_1h


def create_short_training_data(df):
    """Short 거래 훈련 데이터 생성"""
    print("\n📉 Short 훈련 데이터 생성...")
    
    feature_cols = [
        'rsi', 'rsi_change', 'adx', 'adx_pos', 'adx_neg', 'adx_change',
        'dist_ema20', 'dist_ema60', 'dist_ema200', 'atr', 'vol_change',
        'macd_hist', 'stoch_k', 'stoch_d', 'stoch_diff',
        'bb_width', 'vol_ratio', 'ema_slope'
    ]
    
    # Short 진입 조건
    df['short_signal'] = (
        (df['supertrend_direction'] == -1) | 
        (df['rsi'] > 65) |
        (df['close'] < df['ema_60'])
    ).astype(int)
    
    # Short 성공 여부 (가격 하락)
    df['short_success'] = (df['future_return_8h'] < -0.01).astype(int)
    
    # 필터: Short 신호가 있는 경우만
    short_data = df[df['short_signal'] == 1].copy()
    short_data = short_data.dropna(subset=feature_cols + ['short_success'])
    
    X = short_data[feature_cols]
    y = short_data['short_success']
    
    print(f"   Short 샘플: {len(X):,}개")
    print(f"   성공률: {y.mean()*100:.1f}%")
    
    return X, y, feature_cols


def create_long_training_data(df):
    """Long 거래 훈련 데이터 생성"""
    print("\n📈 Long 훈련 데이터 생성...")
    
    feature_cols = [
        'rsi', 'rsi_change', 'adx', 'adx_pos', 'adx_neg', 'adx_change',
        'dist_ema20', 'dist_ema60', 'dist_ema200', 'atr', 'vol_change',
        'macd_hist', 'stoch_k', 'stoch_d', 'stoch_diff',
        'bb_width', 'vol_ratio', 'ema_slope'
    ]
    
    # Long 진입 조건
    df['long_signal'] = (
        (df['supertrend_direction'] == 1) & 
        (df['close'] > df['ema_60']) &
        (df['adx'] > 20)
    ).astype(int)
    
    # Long 성공 여부 (가격 상승)
    df['long_success'] = (df['future_return_8h'] > 0.01).astype(int)
    
    # 필터
    long_data = df[df['long_signal'] == 1].copy()
    long_data = long_data.dropna(subset=feature_cols + ['long_success'])
    
    X = long_data[feature_cols]
    y = long_data['long_success']
    
    print(f"   Long 샘플: {len(X):,}개")
    print(f"   성공률: {y.mean()*100:.1f}%")
    
    return X, y, feature_cols


def create_regime_training_data(df):
    """시장 레짐 분류 훈련 데이터 생성"""
    print("\n🔄 시장 레짐 훈련 데이터 생성...")
    
    feature_cols = [
        'rsi', 'adx', 'dist_ema20', 'dist_ema60', 'dist_ema200',
        'bb_width', 'vol_ratio', 'ema_slope', 'macd_hist'
    ]
    
    # 레짐 레이블
    # 0: SIDEWAYS, 1: BULL, 2: BEAR
    df['regime'] = 0  # 기본값 SIDEWAYS
    
    # BULL: 가격 상승 중
    bull_mask = (
        (df['close'] > df['ema_200']) & 
        (df['ema_20'] > df['ema_60']) &
        (df['future_return_24h'] > 0.02)
    )
    df.loc[bull_mask, 'regime'] = 1
    
    # BEAR: 가격 하락 중
    bear_mask = (
        (df['close'] < df['ema_200']) & 
        (df['ema_20'] < df['ema_60']) &
        (df['future_return_24h'] < -0.02)
    )
    df.loc[bear_mask, 'regime'] = 2
    
    regime_data = df.dropna(subset=feature_cols + ['regime'])
    
    X = regime_data[feature_cols]
    y = regime_data['regime']
    
    print(f"   총 샘플: {len(X):,}개")
    print(f"   SIDEWAYS: {(y==0).sum():,}개 ({(y==0).mean()*100:.1f}%)")
    print(f"   BULL: {(y==1).sum():,}개 ({(y==1).mean()*100:.1f}%)")
    print(f"   BEAR: {(y==2).sum():,}개 ({(y==2).mean()*100:.1f}%)")
    
    return X, y, feature_cols


def train_model(X, y, model_name, n_classes=2):
    """모델 훈련"""
    print(f"\n🤖 {model_name} 모델 훈련...")
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    if n_classes == 2:
        model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            use_label_encoder=False,
            eval_metric='logloss'
        )
    else:
        model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            objective='multi:softmax',
            num_class=n_classes,
            use_label_encoder=False,
            eval_metric='mlogloss'
        )
    
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"   정확도: {accuracy*100:.1f}%")
    
    return model, accuracy


def main():
    print("="*60)
    print("🧠 다중 ML 모델 훈련")
    print("   Short + Long + 레짐 분류")
    print("="*60)
    
    # 데이터 로드
    df = load_and_prepare_data()
    
    # 1. Short 모델 훈련
    X_short, y_short, short_features = create_short_training_data(df.copy())
    short_model, short_acc = train_model(X_short, y_short, "Short", n_classes=2)
    
    # 2. Long 모델 훈련
    X_long, y_long, long_features = create_long_training_data(df.copy())
    long_model, long_acc = train_model(X_long, y_long, "Long", n_classes=2)
    
    # 3. 레짐 분류 모델 훈련
    X_regime, y_regime, regime_features = create_regime_training_data(df.copy())
    regime_model, regime_acc = train_model(X_regime, y_regime, "Regime", n_classes=3)
    
    # 모델 저장
    print("\n💾 모델 저장...")
    
    joblib.dump({
        'model': short_model,
        'features': short_features,
        'accuracy': short_acc
    }, 'short_model.pkl')
    print("   ✅ short_model.pkl 저장")
    
    joblib.dump({
        'model': long_model,
        'features': long_features,
        'accuracy': long_acc
    }, 'long_model.pkl')
    print("   ✅ long_model.pkl 저장")
    
    joblib.dump({
        'model': regime_model,
        'features': regime_features,
        'accuracy': regime_acc
    }, 'regime_model.pkl')
    print("   ✅ regime_model.pkl 저장")
    
    print("\n" + "="*60)
    print("📊 훈련 결과 요약")
    print("="*60)
    print(f"   Short 모델 정확도: {short_acc*100:.1f}%")
    print(f"   Long 모델 정확도: {long_acc*100:.1f}%")
    print(f"   Regime 모델 정확도: {regime_acc*100:.1f}%")
    print("="*60)

if __name__ == "__main__":
    main()
