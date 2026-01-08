import ccxt
import pandas as pd
import json
import os
import time
import logging
from datetime import datetime, timedelta
from market_analyzer import MarketAnalyzer
from strategy import Strategy

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

def fetch_historical_data(symbol, timeframe, start_date_str, end_date_str):
    # Use Bybit (linear/futures)
    exchange = ccxt.bybit({'options': {'defaultType': 'linear'}}) 
    
    since = exchange.parse8601(f"{start_date_str}T00:00:00Z")
    end_ts = exchange.parse8601(f"{end_date_str}T23:59:59Z")
    
    all_ohlcv = []
    print(f"Fetching {symbol} Perpetual data from {start_date_str} to {end_date_str}...")
    
    while since < end_ts:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
            
            current_date = datetime.fromtimestamp(ohlcv[-1][0]/1000).strftime('%Y-%m-%d')
            print(f"  Fetched up to {current_date}... ({len(all_ohlcv)} bars)", end='\r')
            
            if ohlcv[-1][0] >= end_ts:
                break
            time.sleep(exchange.rateLimit / 1000)
        except Exception as e:
            print(f"\nError fetching data: {e}")
            time.sleep(5)
            continue
            
    print(f"\nTotal bars fetched: {len(all_ohlcv)}")
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_continuous_backtest(start_year, end_year, symbol='BTC/USDT', timeframe='15m'):
    print(f"\n=== Running Continuous Backtest from {start_year} to {end_year} [{timeframe}] ===")
    
    # 1. Fetch Data for all years
    all_df = []
    for year in range(start_year, end_year + 1):
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        df = fetch_historical_data(symbol, timeframe, start_date, end_date)
        if not df.empty:
            all_df.append(df)
    
    if not all_df:
        print("No data found.")
        return None
        
    df = pd.concat(all_df).drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    
    # 2. Setup
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error loading config.json: {e}")
        return None

    config['exchange']['symbol'] = symbol
    config['exchange']['timeframe'] = timeframe
    
    class MockClient: 
        def __init__(self): self.id = 'bybit'
    
    analyzer = MarketAnalyzer(MockClient(), config)
    strategy = Strategy(config)
    
    # 3. Analyze
    print("Calculating indicators...")
    df = analyzer.analyze(df)
    df = df.dropna(subset=['ema_200', 'rsi_2', 'atr', 'sma_5', 'ema_long'])
    
    # 4. Simulate
    initial_balance = 10000.0
    balance = initial_balance
    trades = []
    position = None 
    leverage = config['exchange'].get('leverage', 10)
    FEE_RATE = 0.0004
    
    print(f"Running simulation on {len(df)} bars...")
    
    for i in range(len(df)):
        curr_row = df.iloc[i]
        
        # Check Exit
        if position:
            slice_df = df.iloc[i-1:i+1]
            exit_signal = strategy.check_exit(slice_df, position)
            
            reason = None
            exit_price = curr_row['close']
            
            if 'buy' in position['side']:
                if curr_row['low'] <= position['stop_loss']:
                    reason = 'Stop Loss'
                    exit_price = position['stop_loss']
                elif curr_row['high'] >= position['take_profit']:
                    reason = 'Take Profit'
                    exit_price = position['take_profit']
                elif exit_signal and exit_signal.get('action') == 'close':
                    reason = exit_signal.get('reason')
                    exit_price = curr_row['close']
                elif exit_signal and exit_signal.get('action') == 'update_sl':
                    position['stop_loss'] = exit_signal['price']
            else:
                if curr_row['high'] >= position['stop_loss']:
                    reason = 'Stop Loss'
                    exit_price = position['stop_loss']
                elif curr_row['low'] <= position['take_profit']:
                    reason = 'Take Profit'
                    exit_price = position['take_profit']
                elif exit_signal and exit_signal.get('action') == 'close':
                    reason = exit_signal.get('reason')
                    exit_price = curr_row['close']
                elif exit_signal and exit_signal.get('action') == 'update_sl':
                    position['stop_loss'] = exit_signal['price']

            if reason:
                amount = position['amount']
                raw_pnl = amount * (exit_price - position['entry']) if 'buy' in position['side'] else amount * (position['entry'] - exit_price)
                
                # Include entry fee in the trade's PnL for transparency
                entry_fee = position['entry_fee']
                exit_fee = amount * exit_price * FEE_RATE
                net_pnl = raw_pnl - entry_fee - exit_fee
                
                balance += (raw_pnl - exit_fee) # entry_fee was already subtracted from balance at entry
                
                trades.append({
                    'timestamp': curr_row['timestamp'],
                    'year': curr_row['timestamp'].year,
                    'side': position['side'],
                    'pnl': net_pnl,
                    'reason': reason,
                    'balance': balance
                })
                position = None

        # Check Entry
        if not position:
            slice_df = df.iloc[i-1:i+1]
            signal = strategy.check_entry(slice_df)
            
            if signal:
                sl, tp = strategy.calculate_stops(slice_df, signal, curr_row['close'])
                
                risk_pct = config['risk'].get('risk_per_trade_percent', 1.0) / 100
                risk_amt = balance * risk_pct
                sl_dist = abs(curr_row['close'] - sl) / curr_row['close']
                if sl_dist < 0.001: sl_dist = 0.001
                
                pos_value = min(risk_amt / sl_dist, balance * leverage)
                size = pos_value / curr_row['close']
                
                entry_fee = pos_value * FEE_RATE
                balance -= entry_fee
                
                position = {
                    'side': signal,
                    'entry': curr_row['close'],
                    'amount': size,
                    'stop_loss': sl,
                    'take_profit': tp,
                    'entry_fee': entry_fee,
                    'date': curr_row['timestamp']
                }

    if not trades:
        print("No trades found.")
        return

    df_trades = pd.DataFrame(trades)
    
    print("\n" + "="*40)
    print("      CONTINUOUS BACKTEST RESULTS")
    print("="*40)
    
    # Yearly breakdown from the continuous run
    yearly_results = []
    current_year_start_balance = initial_balance
    
    for year in range(start_year, end_year + 1):
        y_trades = df_trades[df_trades['year'] == year]
        if y_trades.empty:
            continue
            
        y_pnl = y_trades['pnl'].sum()
        y_roi = (y_pnl / current_year_start_balance) * 100
        win_rate = (len(y_trades[y_trades['pnl'] > 0]) / len(y_trades)) * 100
        
        print(f"Year {year}: ROI {y_roi:>8.2f}% | Trades {len(y_trades):>3} | Win Rate {win_rate:>6.2f}% | PnL: ${y_pnl:,.2f}")
        
        # Update start balance for next year (continuous compounding)
        current_year_start_balance += y_pnl

    total_roi = ((balance - initial_balance) / initial_balance) * 100
    print("-" * 40)
    print(f"Initial Balance: ${initial_balance:,.2f}")
    print(f"Final Balance:   ${balance:,.2f}")
    print(f"Cumulative ROI:  {total_roi:,.2f}%")
    print("="*40)

def main():
    run_continuous_backtest(2023, 2025)

if __name__ == "__main__":
    main()
