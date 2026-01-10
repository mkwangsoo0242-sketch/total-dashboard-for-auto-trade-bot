import ccxt
import pandas as pd
import pandas_ta as ta
import time

class MarketAnalyzer:
    def __init__(self, exchange_client, config):
        self.exchange = exchange_client
        self.config = config
        self.symbol = config['exchange']['symbol']
        self.timeframe = config['exchange']['timeframe']

    def fetch_ohlcv(self, limit=100):
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"Error fetching OHLCV: {e}")
            return None

    def analyze(self, df):
        if df is None or len(df) < 200:
            return df

        # Bollinger Bands
        bb_length = self.config['strategy']['bb_length']
        bb_std = self.config['strategy']['bb_std']
        bb = df.ta.bbands(close=df['close'], length=bb_length, std=bb_std)
        if bb is not None:
            df = pd.concat([df, bb], axis=1)
            bbu = [c for c in bb.columns if c.startswith('BBU')][0]
            bbl = [c for c in bb.columns if c.startswith('BBL')][0]
            bbm = [c for c in bb.columns if c.startswith('BBM')][0]
            
            df['bb_upper'] = df[bbu]
            df['bb_lower'] = df[bbl]
            df['bb_mid'] = df[bbm]
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']
            df['bb_pos'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
            df['bb_pos'] = df['bb_pos'].astype(float)

        # RSI
        df['rsi_14'] = df.ta.rsi(close=df['close'], length=14)
        df['rsi_2'] = df.ta.rsi(close=df['close'], length=2)

        # ADX
        adx = df.ta.adx(high=df['high'], low=df['low'], close=df['close'], length=14)
        if adx is not None:
            df = pd.concat([df, adx], axis=1)
            adx_col = [c for c in adx.columns if c.startswith('ADX')][0]
            df['adx'] = df[adx_col]

        # ATR & Volatility
        df['atr'] = df.ta.atr(high=df['high'], low=df['low'], close=df['close'], length=14)
        df['volatility'] = df['atr'] / df['close']

        # EMAs
        df['ema_20'] = df.ta.ema(close=df['close'], length=20)
        df['ema_50'] = df.ta.ema(close=df['close'], length=50)
        df['ema_200'] = df.ta.ema(close=df['close'], length=200)
        
        # Long Term EMA (Trend Filter)
        ema_long_period = self.config['strategy'].get('ema_long_period', 4800)
        ema_long = df.ta.ema(close=df['close'], length=ema_long_period)
        
        # DEBUG
        # if ema_long is not None:
        #     print(f"EMA Long Type: {type(ema_long)}")
        #     if isinstance(ema_long, pd.Series):
        #         print(f"EMA Long Dtype: {ema_long.dtype}")
        
        if ema_long is not None:
            if isinstance(ema_long, pd.DataFrame):
                df['ema_long'] = ema_long.iloc[:, 0]
            else:
                df['ema_long'] = ema_long
        else:
            df['ema_long'] = 0.0
        
        # Ensure they are floats and NOT timestamps
        if pd.api.types.is_datetime64_any_dtype(df['ema_long']):
             df['ema_long'] = 0.0
        
        df['close'] = df['close'].astype(float)
        df['ema_long'] = df['ema_long'].astype(float)
        
        df['ema_20_dist'] = (df['close'] - df['ema_20']) / df['ema_20']
        df['ema_50_dist'] = (df['close'] - df['ema_50']) / df['ema_50']
        df['ema_200_dist'] = (df['close'] - df['ema_200']) / df['ema_200']
        df['ema_long_dist'] = (df['close'] - df['ema_long']) / df['ema_long']
        
        # Volume MA
        vol_ma_period = self.config['strategy'].get('volume_ma_period', 20)
        df['volume_ma'] = df['volume'].rolling(window=vol_ma_period).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']

        # SMA 5
        df['sma_5'] = df.ta.sma(length=5)

        # MTF: 4H Donchian Channels (Simulated from 15m)
        # We resample to 4H, calculate Donchian, and map back
        donchian_period = self.config['strategy'].get('donchian_4h_period', 20)
        
        # To avoid data leakage, we need to be careful with resampling
        # Here we use a simpler rolling max/min over the equivalent number of 15m bars
        # 4H = 16 * 15m bars. Donchian 20 (4H) = 20 * 16 = 320 (15m bars)
        df['donchian_high_4h'] = df['high'].rolling(window=donchian_period * 16).max().shift(1)
        df['donchian_low_4h'] = df['low'].rolling(window=donchian_period * 16).min().shift(1)
        df['donchian_pos'] = (df['close'] - df['donchian_low_4h']) / (df['donchian_high_4h'] - df['donchian_low_4h'])

        # Returns
        df['return_1'] = df['close'].pct_change(1)
        df['return_4'] = df['close'].pct_change(4)
        df['return_12'] = df['close'].pct_change(12)

        # Supertrend
        st = df.ta.supertrend(length=10, multiplier=3)
        if st is not None:
            df = pd.concat([df, st], axis=1)
            st_col = [c for c in st.columns if c.startswith('SUPERT_')][0]
            st_dir_col = [c for c in st.columns if c.startswith('SUPERTd_')][0]
            df['supertrend'] = df[st_col]
            df['supertrend_dir'] = df[st_dir_col] # 1 for up, -1 for down

        return df
