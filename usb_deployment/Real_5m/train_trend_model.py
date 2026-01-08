import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, classification_report
import joblib
import pandas_ta as ta
from strategy import add_indicators

def prepare_trend_data(df, max_hold=48):
    """
    데이터 준비 및 메타 라벨링 (1시간봉 기준)
    """
    df = df.copy()
    
    # 1. Indicators
    df = add_indicators(df)
    
    # 2. Features for ML
    df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
    df['dist_ema60'] = (df['close'] - df['ema_60']) / df['ema_60']
    df['rsi_change'] = df['rsi'].diff()
    df['adx_change'] = df['adx'].diff()
    df['vol_change'] = df['volume'].pct_change()
    
    # MACD & Stochastic RSI Features
    df['stoch_diff'] = df['stoch_k'] - df['stoch_d']
    
    # New Features (V3)
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    df['vol_ratio'] = df['volume'] / df['vol_ma20']
    df['ema_slope'] = df['ema_20'].pct_change() * 100
    
    print(f"Before dropna: {len(df)}")
    # print(f"NaN counts:\n{df.isna().sum()}")
    
    # Exclude supertrend_long/short from dropna check
    cols_to_check = [c for c in df.columns if c not in ['supertrend_long', 'supertrend_short']]
    df.dropna(subset=cols_to_check, inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    features_list = []
    labels = []
    
    print(f"Labeling data... (Total rows: {len(df)})")
    
    # 3. Meta-Labeling
    # 전략의 진입 조건이 만족된 시점만 학습 데이터로 사용
    
    for i in range(len(df) - max_hold):
        row = df.iloc[i]
        
        # Base Strategy Entry Condition
        # Long: Close > EMA60 and Supertrend == 1 and ADX > 25
        # Short: Close < EMA60 and Supertrend == -1 and ADX > 25
        
        entry_type = None
        if row['close'] > row['ema_60'] and row['supertrend_direction'] == 1 and row['adx'] > 25:
            entry_type = 'long'
        elif row['close'] < row['ema_60'] and row['supertrend_direction'] == -1 and row['adx'] > 25:
            entry_type = 'short'
            
        if entry_type:
            entry_price = row['close']
            atr = row['atr']
            
            # Outcome determination
            outcome = 0 # Default Loss
            
            tp_mult = 3.0
            sl_mult = 1.2
            
            if entry_type == 'long':
                tp_price = entry_price + (atr * tp_mult)
                sl_price = entry_price - (atr * sl_mult)
                
                for j in range(1, max_hold + 1):
                    future_row = df.iloc[i + j]
                    if future_row['low'] <= sl_price:
                        outcome = 0 # Hit SL
                        break
                    elif future_row['high'] >= tp_price:
                        outcome = 1 # Hit TP
                        break
                    # If Supertrend flips, we could consider it an exit, but for labeling "high quality" trades,
                    # we might prefer those that hit TP or don't hit SL.
                    # Let's keep it simple: Hit TP = Win, Hit SL = Loss.
                    
            elif entry_type == 'short':
                tp_price = entry_price - (atr * tp_mult)
                sl_price = entry_price + (atr * sl_mult)
                
                for j in range(1, max_hold + 1):
                    future_row = df.iloc[i + j]
                    if future_row['high'] >= sl_price:
                        outcome = 0 # Hit SL
                        break
                    elif future_row['low'] <= tp_price:
                        outcome = 1 # Hit TP
                        break
            
            # Collect Feature
            feature_dict = {
                'rsi': row['rsi'],
                'rsi_change': row['rsi'],
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
            features_list.append(feature_dict)
            labels.append(outcome)
            
    return pd.DataFrame(features_list), pd.Series(labels)

def train_trend_model(data_path, model_path='trend_xgb.pkl'):
    print(f"Loading data from {data_path}")
    df = pd.read_csv(data_path)
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
    df_1h.reset_index(inplace=True)
    
    X, y = prepare_trend_data(df_1h)
    
    if len(X) == 0:
        print("No training data found (no entry signals).")
        return
        
    print(f"Training data size: {len(X)}")
    print(f"Class distribution:\n{y.value_counts()}")
    
    # Split
    train_size = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:train_size], X.iloc[train_size:]
    y_train, y_test = y.iloc[:train_size], y.iloc[train_size:]
    
    # XGBoost
    model = xgb.XGBClassifier(
        objective='binary:logistic',
        eval_metric='logloss',
        use_label_encoder=False,
        n_jobs=-1
    )
    
    # Hyperparameter Tuning
    param_dist = {
        'n_estimators': [100, 200, 300],
        'learning_rate': [0.01, 0.05, 0.1],
        'max_depth': [3, 5, 7],
        'min_child_weight': [1, 3, 5],
        'subsample': [0.6, 0.8, 1.0],
        'colsample_bytree': [0.6, 0.8, 1.0],
        'gamma': [0, 0.1, 0.2]
    }
    
    tscv = TimeSeriesSplit(n_splits=3)
    random_search = RandomizedSearchCV(
        model, param_distributions=param_dist, n_iter=20,
        scoring='precision', # Maximize Precision (Win Rate)
        cv=tscv, verbose=1, random_state=42, n_jobs=-1
    )
    
    print("Starting Hyperparameter Tuning...")
    random_search.fit(X_train, y_train)
    
    best_model = random_search.best_estimator_
    print(f"Best Parameters: {random_search.best_params_}")
    
    # Evaluate
    y_pred = best_model.predict(X_test)
    y_prob = best_model.predict_proba(X_test)[:, 1]
    
    print("Test Set Evaluation:")
    print(classification_report(y_test, y_pred))
    print(f"Precision: {precision_score(y_test, y_pred):.4f}")
    
    # Save
    joblib.dump(best_model, model_path)
    print(f"Model saved to {model_path}")

if __name__ == "__main__":
    train_trend_model('data/btc_usdt_5m_3y.csv')
