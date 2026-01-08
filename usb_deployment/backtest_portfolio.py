"""
4대 ML 봇 통합 포트폴리오 백테스트 (Fixed Features)
"""
import pandas as pd
import numpy as np
import joblib
import os
import warnings
warnings.filterwarnings('ignore')

# 설정
DATA_PATH = "portfolio_data.csv"
BASE_DIR = "/home/ser1/새 폴더/btc/usdt 봇 통합관리/usb_deployment"
INITIAL_CAPITAL_PER_BOT = 100000

print(f"💰 통합 백테스트 시작 (총 자본금: {INITIAL_CAPITAL_PER_BOT * 4:,}원)")
print("📊 데이터 로딩 및 지표 계산 중...")
df_raw = pd.read_csv(DATA_PATH)
df_raw['datetime'] = pd.to_datetime(df_raw['timestamp'], unit='ms')
df_raw = df_raw.set_index('datetime')
df_raw = df_raw.sort_index()

def calculate_full_indicators(df):
    # EMA
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_60'] = df['close'].ewm(span=60, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # Bollinger Bands
    rolling_mean = df['close'].rolling(20).mean()
    rolling_std = df['close'].rolling(20).std()
    df['bb_upper'] = rolling_mean + (rolling_std * 2)
    df['bb_lower'] = rolling_mean - (rolling_std * 2)
    df['bb_middle'] = rolling_mean 
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / rolling_mean
    
    # Stochastic (Not used in features but calculated just in case)
    low_min = df['low'].rolling(14).min()
    high_max = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - low_min) / (high_max - low_min)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()
    df['stoch_diff'] = df['stoch_k'] - df['stoch_d']
    
    # ATR
    tr1 = df['high'] - df['low']
    tr2 = abs(df['high'] - df['close'].shift())
    tr3 = abs(df['low'] - df['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    # ADX (Simple)
    df['adx'] = 0 
    
    # Volatility
    df['vol_change'] = df['volume'].pct_change()
    df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    
    # Custom Features
    df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
    df['dist_ema60'] = (df['close'] - df['ema_60']) / df['ema_60']
    df['dist_ema200'] = (df['close'] - df['ema_200']) / df['ema_200']
    df['rsi_change'] = df['rsi'].diff()
    df['ema_slope'] = df['ema_20'].diff()
    
    return df.fillna(0)

df_5m = calculate_full_indicators(df_raw.copy())

def run_simulation(name, folder, model_names, features, timeframe, leverage_bull, leverage_bear, risk_bull, risk_bear, threshold=0.5):
    print(f"\n🚀 [{name}] 등판 준비...")
    try:
        model_dir = os.path.join(BASE_DIR, folder)
        short_model = joblib.load(os.path.join(model_dir, model_names[0]))['model']
        long_model = joblib.load(os.path.join(model_dir, model_names[1]))['model']
        regime_model = joblib.load(os.path.join(model_dir, model_names[2]))['model']
    except Exception as e:
        print(f"❌ {name} 로드 실패: {e}")
        return None

    if timeframe == '5m':
        df = df_5m.copy()
    else:
        df_resampled = df_raw.resample(timeframe).agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        df = calculate_full_indicators(df_resampled)
    
    missing_cols = set(features) - set(df.columns)
    for c in missing_cols:
        df[c] = 0
        
    X = df[features].values
    
    print(f"   🔮 예측 중... ({len(df)} candles)")
    df['regime'] = regime_model.predict(X)
    df['long_prob'] = long_model.predict_proba(X)[:, 1]
    df['short_prob'] = short_model.predict_proba(X)[:, 1]
    
    print(f"   ⚔️ 전투 시작!")
    balance = INITIAL_CAPITAL_PER_BOT
    position = 0
    entry_price = 0
    equity_curve = []
    
    taker_fee = 0.0004
    slippage = 0.0003
    
    records = df.to_dict('records')
    
    for row in records:
        price = row['close']
        atr = row['atr']
        if atr <= 0: atr = price * 0.01
        
        if position != 0:
            is_long = position > 0
            exit_price = None
            if is_long:
                sl = entry_price - atr
                tp = entry_price + (atr * 4) 
                if timeframe == '5m': tp = entry_price + (atr * 10) 
                
                if row['low'] <= sl: exit_price = sl * (1 - slippage)
                elif row['high'] >= tp: exit_price = tp * (1 - slippage)
            else:
                sl = entry_price + atr
                tp = entry_price - (atr * 3) 
                if timeframe == '5m': tp = entry_price - (atr * 10)

                if row['high'] >= sl: exit_price = sl * (1 + slippage)
                elif row['low'] <= tp: exit_price = tp * (1 + slippage)
                
            if exit_price:
                if is_long: pnl = (exit_price - entry_price) * position
                else: pnl = (entry_price - exit_price) * abs(position)
                fee = abs(position) * exit_price * taker_fee
                balance += (pnl - fee)
                position = 0
        
        if position == 0 and balance > 0:
            regime = int(row['regime'])
            action = 'skip'
            lev = 1
            risk = 0.01
            
            if regime == 1: 
                action = 'long'
                lev = leverage_bull
                risk = risk_bull
            elif regime == 2: 
                action = 'short'
                lev = leverage_bear
                risk = risk_bear
            
            signal = None
            if action == 'long' and row['long_prob'] > threshold: signal = 'long'
            elif action == 'short' and row['short_prob'] > threshold: signal = 'short'
            
            if signal:
                sl_dist = atr
                if sl_dist == 0: continue
                risk_amt = balance * risk
                pos_val = min(risk_amt / (sl_dist/price), balance * lev)
                fee = pos_val * taker_fee
                balance -= fee
                qty = (pos_val - fee) / price
                position = qty if signal == 'long' else -qty
                entry_price = price
                
        equity_curve.append(balance)
        
    s_equity = pd.Series(equity_curve, index=df.index)
    aligned_equity = s_equity.reindex(df_raw.index, method='ffill').fillna(INITIAL_CAPITAL_PER_BOT)
    roi = (aligned_equity.iloc[-1] - INITIAL_CAPITAL_PER_BOT) / INITIAL_CAPITAL_PER_BOT * 100
    print(f"   🏁 종료 잔고: {aligned_equity.iloc[-1]:,.0f}원 ({roi:,.0f}%)")
    
    return aligned_equity

# 피처 정의
FEATS_7 = ['rsi', 'rsi_change', 'dist_ema20', 'dist_ema60', 'dist_ema200', 'atr', 'vol_change']
FEATS_9 = ['rsi', 'adx', 'dist_ema20', 'dist_ema60', 'dist_ema200', 'bb_width', 'vol_ratio', 'ema_slope', 'macd_hist']

# 1. Crazy Bull (5m) - 7 features (확인됨)
eq_5m = run_simulation("Crazy Bull (5m)", "Real_5m", 
                       ['short_model.pkl', 'long_model.pkl', 'regime_model.pkl'], 
                       FEATS_7,
                       "5m", 30, 10, 0.15, 0.05)

# 2. Deploy 15m - 9 features (일반적으로)
eq_15m = run_simulation("Deploy_15m (15m)", "Deploy_15m", 
                        ['lgbm_short.pkl', 'lgbm_long.pkl', 'lgbm_regime.pkl'], 
                        FEATS_9,
                        "15min", 20, 10, 0.05, 0.03)

# 3. Bybit 1h - 9 features
eq_1h = run_simulation("Bybit_1h (1h)", "Bybit_1h", 
                       ['xgb_short_1h.pkl', 'xgb_long_1h.pkl', 'xgb_regime_1h.pkl'], 
                       FEATS_9,
                       "1h", 25, 15, 0.05, 0.03)

# 4. Ultimate 100m - 9 features (에러 메시지에서 확인됨)
eq_ult = run_simulation("Ultimate_100m (1h)", "Ultimate_100m", 
                        ['short_model.pkl', 'long_model.pkl', 'regime_model.pkl'], 
                        FEATS_9,
                        "1h", 20, 10, 0.05, 0.03)

print("\n📊 포트폴리오 통합 중...")
total_equity = pd.DataFrame(index=df_raw.index)
total_equity['Total'] = 0

if eq_5m is not None: total_equity['Total'] += eq_5m
if eq_15m is not None: total_equity['Total'] += eq_15m
if eq_1h is not None: total_equity['Total'] += eq_1h
if eq_ult is not None: total_equity['Total'] += eq_ult

final_val = total_equity['Total'].iloc[-1]
initial_val = INITIAL_CAPITAL_PER_BOT * 4
total_roi = (final_val - initial_val) / initial_val * 100

print("\n========================================================")
print(f"🏆 Ultimate Portfolio Result (4 Bots)")
print("========================================================")
print(f"💰 초기 투자: {initial_val:,.0f}원 (각 10만원)")
print(f"💵 최종 평가: {final_val:,.0f}원")
print(f"🚀 통합 수익률: {total_roi:,.0f}% ({total_roi/100:,.1f}배)")
print("========================================================")
total_equity['Year'] = total_equity.index.year
yearly = total_equity.groupby('Year')['Total'].last()
prev = initial_val
for year, val in yearly.items():
    yr_roi = (val - prev) / prev * 100
    print(f"   {year}년: {yr_roi:+.1f}% \t잔고: {val:,.0f}원")
    prev = val
print("========================================================")
