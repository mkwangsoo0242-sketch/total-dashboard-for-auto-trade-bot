import pandas as pd
import pandas_ta as ta

def add_indicators(df):
    """
    전략에 필요한 보조지표를 계산하여 DataFrame에 추가하는 함수
    """
    df = df.copy()
    
    # 1. EMA (Exponential Moving Average) - 20, 60
    df['ema_20'] = ta.ema(df['close'], length=20)
    df['ema_60'] = ta.ema(df['close'], length=60)
    
    # 2. Supertrend (10, 2)
    st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=2.0)
    # pandas_ta returns columns like SUPERT_10_2.0, SUPERTd_10_2.0, SUPERTl_10_2.0, SUPERTs_10_2.0
    # We rename them to standard names
    st_cols = st.columns
    df['supertrend'] = st[st_cols[0]] # Main line
    df['supertrend_direction'] = st[st_cols[1]] # Direction (1: Long, -1: Short)
    df['supertrend_long'] = st[st_cols[2]]
    df['supertrend_short'] = st[st_cols[3]]
    
    # 3. ADX (Average Directional Index) - 14
    adx = ta.adx(df['high'], df['low'], df['close'], length=14)
    # Returns ADX_14, DMP_14, DMN_14
    df['adx'] = adx[adx.columns[0]]
    df['adx_pos'] = adx[adx.columns[1]]
    df['adx_neg'] = adx[adx.columns[2]]
    
    # 4. RSI (Relative Strength Index) - 14
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    # 5. ATR (Average True Range) - 14
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    # 6. MACD (12, 26, 9)
    macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
    # Returns MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
    df['macd'] = macd[macd.columns[0]]
    df['macd_hist'] = macd[macd.columns[1]]
    df['macd_signal'] = macd[macd.columns[2]]
    
    # 7. Stochastic RSI (14, 14, 3, 3)
    stochrsi = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
    # Returns STOCHRSIk_14_14_3_3, STOCHRSId_14_14_3_3
    df['stoch_k'] = stochrsi[stochrsi.columns[0]]
    df['stoch_d'] = stochrsi[stochrsi.columns[1]]
    
    # 8. Bollinger Bands (20, 2)
    bb = ta.bbands(df['close'], length=20, std=2)
    # Returns BBL_20_2.0, BBM_20_2.0, BBU_20_2.0, BBB_20_2.0, BBP_20_2.0
    df['bb_lower'] = bb[bb.columns[0]]
    df['bb_middle'] = bb[bb.columns[1]]
    df['bb_upper'] = bb[bb.columns[2]]
    
    # 9. Volume MA (20)
    df['vol_ma20'] = ta.sma(df['volume'], length=20)
    
    return df
