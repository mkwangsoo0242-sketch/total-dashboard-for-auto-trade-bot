import pandas as pd
import pandas_ta as ta
import numpy as np
import os
import json
import joblib
import logging
import requests
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional, List

logger = logging.getLogger('strategy')

@dataclass
class AdaptiveConfig:
    # Common
    leverage: float = 1.0
    fee_taker: float = 0.0006
    
    # Regime Detection
    adx_trending_min: int = 25
    adx_ranging_max: int = 20
    
    # Risk Management
    trend_sl_atr: float = 2.0
    range_sl_atr: float = 1.5
    
    # Session
    session_start_hour: int = 0
    session_end_hour: int = 23

def add_indicators(df):
    """
    전략에 필요한 모든 보조지표를 계산하여 DataFrame에 추가하는 함수
    (Adaptive Strategy + ML Features 통합 버전)
    """
    df = df.copy()
    
    # 1. Trend (EMA)
    df['ema_20'] = ta.ema(df['close'], length=20)
    df['ema_50'] = ta.ema(df['close'], length=50) # For Adaptive Strategy
    df['ema_60'] = ta.ema(df['close'], length=60)
    df['ema_200'] = ta.ema(df['close'], length=200)
    
    # 2. Supertrend (10, 2)
    st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=2.0)
    if st is not None:
        st_cols = st.columns
        df['supertrend'] = st[st_cols[0]]
        df['supertrend_direction'] = st[st_cols[1]]
    
    # 3. ADX (Average Directional Index) - 14
    adx = ta.adx(df['high'], df['low'], df['close'], length=14)
    if adx is not None:
        df['adx'] = adx.iloc[:, 0]
        df['adx_pos'] = adx.iloc[:, 1]
        df['adx_neg'] = adx.iloc[:, 2]
    
    # 4. RSI (Relative Strength Index) - 14
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    # 5. ATR (Average True Range) - 14
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    # 6. MACD (12, 26, 9)
    macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
    if macd is not None:
        df['macd'] = macd.iloc[:, 0]
        df['macd_hist'] = macd.iloc[:, 1]
        df['macd_signal'] = macd.iloc[:, 2]
    
    # 7. Stochastic RSI (14, 14, 3, 3)
    stochrsi = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
    if stochrsi is not None:
        df['stoch_k'] = stochrsi.iloc[:, 0]
        df['stoch_d'] = stochrsi.iloc[:, 1]
    
    # 8. Bollinger Bands (20, 2)
    bb = ta.bbands(df['close'], length=20, std=2.0)
    if bb is not None:
        df['bb_lower'] = bb.iloc[:, 0]
        df['bb_middle'] = bb.iloc[:, 1]
        df['bb_upper'] = bb.iloc[:, 2]
    
    # 9. Volume MA (20)
    df['vol_ma20'] = ta.sma(df['volume'], length=20)
    
    # 10. Additional Features for ML
    df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
    df['dist_ema60'] = (df['close'] - df['ema_60']) / df['ema_60']
    df['rsi_change'] = df['rsi'].diff()
    df['adx_change'] = df['adx'].diff()
    df['vol_change'] = df['volume'].pct_change()
    df['stoch_diff'] = df['stoch_k'] - df['stoch_d']
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    df['vol_ratio'] = df['volume'] / df['vol_ma20']
    df['ema_slope'] = df['ema_20'].pct_change() * 100
    
    # Adaptive Strategy specific naming consistency
    df['ema_trend'] = df['ema_50']
    df['bb_mid'] = df['bb_middle']
    
    return df

class AdaptiveStrategy:
    """통합 적응형 전략 클래스 (백테스트 및 실거래 공용)"""
    def __init__(self, config: AdaptiveConfig = None, model_path: str = 'trend_xgb.pkl'):
        self.config = config or AdaptiveConfig()
        self.model = None
        if model_path and os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
                logger.info(f"ML Model loaded: {model_path}")
            except Exception as e:
                logger.error(f"Error loading ML Model: {e}")

    def get_regime(self, row) -> str:
        if row['adx'] >= self.config.adx_trending_min:
            return 'trending'
        elif row['adx'] <= self.config.adx_ranging_max:
            return 'ranging'
        return 'ranging'

    def get_signal(self, df: pd.DataFrame, check_time: bool = True) -> Dict:
        """신호 생성 (ML 필터 포함)"""
        row = df.iloc[-1]
        regime = self.get_regime(row)
        
        # 시간 필터 체크 (실거래용)
        if check_time:
            from datetime import datetime, timezone, timedelta
            KST = timezone(timedelta(hours=9))
            hour = datetime.now(KST).hour
            if not (self.config.session_start_hour <= hour <= self.config.session_end_hour):
                return {'side': 'none', 'regime': regime, 'reason': 'Outside trading hours'}

        side = 'none'
        reason = 'No Signal'

        # 로직 A: Trending
        if regime == 'trending':
            if row['close'] > row['ema_trend'] and 55 < row['rsi'] < 75:
                side = 'buy'
                reason = 'Trend Bullish Momentum'
            elif row['close'] < row['ema_trend'] and 25 < row['rsi'] < 45:
                side = 'sell'
                reason = 'Trend Bearish Momentum'
                
        # 로직 B: Ranging
        elif regime == 'ranging':
            if row['close'] < row['bb_lower'] and row['rsi'] < 25:
                side = 'buy'
                reason = 'Range Deep Dip'
            elif row['close'] > row['bb_upper'] and row['rsi'] > 75:
                side = 'sell'
                reason = 'Range Deep Peak'
        
        # ML 필터 적용
        if side != 'none' and self.model:
            try:
                features = pd.DataFrame([{
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
                    'trade_type': 1 if side == 'buy' else 0
                }])
                
                prob = self.model.predict_proba(features)[0][1]
                if prob < 0.55: # 임계값
                    return {'side': 'none', 'regime': regime, 'reason': f'Filtered by ML ({prob:.4f})'}
                reason += f" (ML Prob: {prob:.4f})"
            except Exception as e:
                logger.error(f"ML Prediction Error: {e}")
                return {'side': 'none', 'regime': regime, 'reason': 'ML Error'}

        return {'side': side, 'regime': regime, 'reason': reason}

    def check_exit(self, df: pd.DataFrame, position_side: str, entry_regime: str) -> Tuple[bool, str]:
        """익절/손절 체크"""
        row = df.iloc[-1]
        
        if position_side == 'buy':
            if entry_regime == 'ranging' and row['rsi'] > 50:
                return True, "Range RSI Mid Exit"
            if entry_regime == 'trending' and row['close'] < row['ema_trend']:
                return True, "Trend Reversal Exit"
        else: # sell
            if entry_regime == 'ranging' and row['rsi'] < 50:
                return True, "Range RSI Mid Exit"
            if entry_regime == 'trending' and row['close'] > row['ema_trend']:
                return True, "Trend Reversal Exit"
        
        return False, ""

    def backtest(self, df: pd.DataFrame, initial_capital: float = 100.0) -> Dict:
        """백테스트 엔진"""
        df = add_indicators(df)
        capital = initial_capital
        position = None 
        entry_price = 0
        position_size = 0 
        stop_loss = 0
        regime_at_entry = 'unknown'
        
        trades = []
        equity_curve = []
        
        # 지표 안정화를 위해 100개 이후부터 시작
        for i in range(100, len(df)):
            row = df.iloc[i]
            current_time = df.index[i]
            current_price = row['close']
            atr = row['atr']
            
            # 1. Exit Logic
            if position:
                should_exit = False
                exit_reason = ""
                
                # ATR 기반 스톱로스
                if position == 'buy' and current_price <= stop_loss:
                    should_exit, exit_reason = True, "Stop Loss"
                elif position == 'sell' and current_price >= stop_loss:
                    should_exit, exit_reason = True, "Stop Loss"
                
                # 전략 기반 종료
                if not should_exit:
                    should_exit, exit_reason = self.check_exit(df.iloc[:i+1], position, regime_at_entry)
                
                if should_exit:
                    fee = self.config.fee_taker * 2
                    pnl_pct = (current_price - entry_price) / entry_price if position == 'buy' else (entry_price - current_price) / entry_price
                    net_pnl_pct = pnl_pct - fee
                    pnl_amount = position_size * net_pnl_pct
                    capital += pnl_amount
                    
                    trades.append({
                        'entry_time': entry_time,
                        'exit_time': current_time,
                        'side': position,
                        'pnl_net': pnl_amount,
                        'return': net_pnl_pct * self.config.leverage,
                        'reason': exit_reason
                    })
                    position = None
            
            # 2. Entry Logic
            if not position:
                # 시간 필터 제외 (백테스트는 전체 시간 대상)
                signal = self.get_signal(df.iloc[:i+1], check_time=False)
                if signal['side'] != 'none':
                    position = signal['side']
                    entry_price = current_price
                    entry_time = current_time
                    regime_at_entry = signal['regime']
                    
                    position_size = capital * self.config.leverage
                    sl_dist = atr * (self.config.trend_sl_atr if regime_at_entry == 'trending' else self.config.range_sl_atr)
                    stop_loss = entry_price - sl_dist if position == 'buy' else entry_price + sl_dist

            equity_curve.append(capital)
            
        # 결과 계산
        total_return = (capital - initial_capital) / initial_capital
        win_rate = len([t for t in trades if t['pnl_net'] > 0]) / len(trades) if trades else 0
        
        # MDD 계산
        peak = initial_capital
        max_dd = 0
        for eq in equity_curve:
            if eq > peak: peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd: max_dd = dd
            
        return {
            'total_return': total_return,
            'win_rate': win_rate,
            'max_drawdown': max_dd,
            'trades': trades,
            'final_capital': capital
        }

def _interval_to_ms(interval: str) -> int:
    """분 단위 인터벌을 밀리초로 변환"""
    intervals = {
        "1": 60_000, "3": 3 * 60_000, "5": 5 * 60_000, "15": 15 * 60_000,
        "30": 30 * 60_000, "60": 60 * 60_000, "120": 120 * 60_000,
        "240": 240 * 60_000, "360": 360 * 60_000, "720": 720 * 60_000,
        "D": 24 * 60 * 60_000, "W": 7 * 24 * 60 * 60_000, "M": 30 * 24 * 60 * 60_000
    }
    if interval in intervals:
        return intervals[interval]
    raise ValueError(f"Unsupported interval: {interval}")

def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int, limit: int = 1000) -> pd.DataFrame:
    """Bybit V5 Market API를 사용하여 클라인 데이터 조회"""
    url = "https://api.bybit.com/v5/market/kline"
    window = _interval_to_ms(interval) * limit
    session = requests.Session()
    rows_by_time: Dict[int, List[str]] = {}
    current_start = start_ms
    
    while current_start < end_ms:
        current_end = min(current_start + window - 1, end_ms)
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "start": current_start,
            "end": current_end,
            "limit": limit,
        }
        try:
            resp = session.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("retCode") != 0:
                logger.error(f"Bybit API Error: {data.get('retMsg')}")
                break
            
            rows = data.get("result", {}).get("list", [])
            if not rows:
                break
                
            for r in rows:
                ts = int(r[0])
                if ts not in rows_by_time:
                    rows_by_time[ts] = r
            
            if current_end >= end_ms:
                break
            current_start = current_end + 1
            time.sleep(0.1)
        except Exception as e:
            logger.error(f"Error fetching klines: {e}")
            break
            
    if not rows_by_time:
        return pd.DataFrame()
        
    timestamps = sorted(rows_by_time.keys())
    records = []
    for ts in timestamps:
        r = rows_by_time[ts]
        records.append({
            "time": datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": float(r[5]),
            "turnover": float(r[6]),
        })
        
    df = pd.DataFrame(records)
    df.set_index("time", inplace=True)
    return df
