import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
import os

def fetch_ohlcv(symbol, timeframe, since, limit=1000):
    exchange = ccxt.binance()
    all_ohlcv = []
    
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since, limit)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
            # Convert timestamp to datetime for progress tracking
            current_date = datetime.fromtimestamp(ohlcv[-1][0] / 1000)
            print(f"Collected up to: {current_date}")
            time.sleep(0.5) # Rate limit
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
            continue
            
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def update_data(symbol, timeframe, filename):
    os.makedirs('data', exist_ok=True)
    
    if os.path.exists(filename):
        existing_df = pd.read_csv(filename)
        existing_df['datetime'] = pd.to_datetime(existing_df['datetime'])
        last_timestamp = existing_df['timestamp'].max()
        since = int(last_timestamp) + 1 # Fetch data after the last recorded timestamp
        print(f"Appending new data for {symbol} {timeframe} since {datetime.fromtimestamp(last_timestamp / 1000)}...")
        
        new_df = fetch_ohlcv(symbol, timeframe, since)
        if not new_df.empty:
            updated_df = pd.concat([existing_df, new_df], ignore_index=True)
            updated_df.drop_duplicates(subset=['timestamp'], inplace=True)
            updated_df.sort_values('timestamp', inplace=True)
            updated_df.to_csv(filename, index=False)
            print(f"Appended {len(new_df)} new rows to {filename}")
        else:
            print("No new data to append.")
            
    else:
        # 3 years ago
        start_date = datetime.now() - timedelta(days=365*3)
        since = int(start_date.timestamp() * 1000)
        
        print(f"Fetching {symbol} {timeframe} data since {start_date}...")
        df = fetch_ohlcv(symbol, timeframe, since)
        
        if not df.empty:
            df.to_csv(filename, index=False)
            print(f"Saved initial data to {filename}")
        else:
            print("No initial data fetched.")

if __name__ == "__main__":
    symbol = 'BTC/USDT'
    timeframe = '5m'
    filename = f"data/btc_usdt_{timeframe}_3y.csv"
    update_data(symbol, timeframe, filename)
