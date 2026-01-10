import pandas as pd
import numpy as np
from strategy import Strategy30m, resample_to_30m

def get_mdd(equity_series):
    if len(equity_series) == 0: return 0
    equity_series = pd.Series(equity_series)
    roll_max = equity_series.cummax()
    drawdown = (equity_series - roll_max) / roll_max
    return drawdown.min() * 100

def final_test():
    path_17_19 = "../btc_2015_2019_5m.csv"
    path_20_21 = "../btc_2020_2021_5m.csv"
    path_22 = "../btc_2022_2022_5m.csv"
    path_23_25 = "../btc_3years_5m_binance.csv"

    print("Loading and merging data...")
    df_17_19 = pd.read_csv(path_17_19)
    df_20_21 = pd.read_csv(path_20_21)
    df_22 = pd.read_csv(path_22)
    df_23_25 = pd.read_csv(path_23_25)
    
    dfs = [df_17_19, df_20_21, df_22, df_23_25]
    for df in dfs:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            
    df_all = pd.concat(dfs)
    df_all.set_index('timestamp', inplace=True)
    df_all = df_all[~df_all.index.duplicated(keep='first')].sort_index()
    
    df_30m = resample_to_30m(df_all)
    
    strat = Strategy30m(initial_leverage=10, mode='extreme_growth')
    df_30m = strat.populate_indicators(df_30m)
    
    years = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
    
    print(f"\n{'Year':<6} | {'Final Bal':<12} | {'ROI %':<10} | {'MDD %':<8} | {'Trades':<8} | {'WinRate %':<10}")
    print("-" * 75)
    
    for year in years:
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        final_bal, trades, equity_curve = strat.backtest(df_30m, start_date=start_date, end_date=end_date, initial_balance=100)
        
        roi = (final_bal / 100 - 1) * 100
        mdd = get_mdd(equity_curve)
        
        win_rate = 0
        if len(trades) > 0:
            trades_df = pd.DataFrame(trades)
            win_rate = (trades_df['roi'] > 0).mean() * 100
            
        print(f"{year:<6} | ${final_bal:<11.2f} | {roi:<9.2f}% | {mdd:<7.2f}% | {len(trades):<8} | {win_rate:<10.2f}%")

if __name__ == "__main__":
    final_test()
