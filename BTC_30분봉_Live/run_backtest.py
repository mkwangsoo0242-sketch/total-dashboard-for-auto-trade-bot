import pandas as pd
import numpy as np
from strategy import Strategy30m, resample_to_30m
import matplotlib.pyplot as plt

def get_mdd(equity_series):
    if len(equity_series) == 0: return 0
    equity_series = pd.Series(equity_series)
    roll_max = equity_series.cummax()
    drawdown = (equity_series - roll_max) / roll_max
    return drawdown.min() * 100

def run_live_simulation():
    # 데이터 경로 설정 (부모 디렉토리의 데이터 사용)
    path_17_19 = "../btc_2015_2019_5m.csv"
    path_20_21 = "../btc_2020_2021_5m.csv"
    path_22 = "../btc_2022_2022_5m.csv"
    path_23_25 = "../btc_3years_5m_binance.csv"

    print("전체 데이터 로딩 및 통합 중...")
    try:
        df_17_19 = pd.read_csv(path_17_19)
        df_20_21 = pd.read_csv(path_20_21)
        df_22 = pd.read_csv(path_22)
        df_23_25 = pd.read_csv(path_23_25)
    except FileNotFoundError as e:
        print(f"데이터 파일을 찾을 수 없습니다: {e}")
        return

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
    
    print("30분봉 리샘플링 및 지표 계산 중...")
    df_30m = resample_to_30m(df_all)
    
    # 전략 초기화 (레버리지 10, 익스트림 성장 모드)
    strat = Strategy30m(initial_leverage=10, mode='extreme_growth')
    df_30m = strat.populate_indicators(df_30m)
    
    # --- 실거래 시뮬레이션 설정 ---
    initial_balance = 100.0  # 100 USDT로 시작
    fee_rate = 0.0006  # 0.05% 수수료 + 0.01% 슬리피지 = 0.06%
    
    # 전략의 수수료율 업데이트 (백테스트 내부에서 사용하도록 하려면 Strategy30m 클래스 수정이 필요할 수 있으나, 
    # 현재는 클래스 내부 fee_rate가 0.0005로 고정되어 있음. 이를 반영하여 결과 해석)
    
    print(f"실거래 시뮬레이션 시작: {df_30m.index[0]} ~ {df_30m.index[-1]}")
    print(f"시작 금액: {initial_balance} USDT | 수수료+슬리피지: {fee_rate*100:.3f}% | 연속 복리 적용")
    
    final_bal, trades, equity_curve = strat.backtest(
        df_30m, 
        initial_balance=initial_balance,
        fee_rate=fee_rate,
        verbose=False
    )
    
    # 결과 분석
    total_roi = (final_bal / initial_balance - 1) * 100
    mdd = get_mdd(equity_curve)
    
    if len(trades) > 0:
        trades_df = pd.DataFrame(trades)
        win_rate = (trades_df['roi'] > 0).mean() * 100
        avg_roi = trades_df['roi'].mean()
        max_win = trades_df['roi'].max()
        max_loss = trades_df['roi'].min()
    else:
        win_rate = avg_roi = max_win = max_loss = 0

    print("\n" + "="*50)
    print("      [실거래 시뮬레이션 최종 보고서]      ")
    print("="*50)
    print(f"테스트 기간: {df_30m.index[0].date()} ~ {df_30m.index[-1].date()}")
    print(f"초기 자본: {initial_balance:,.2f} USDT")
    print(f"최종 자본: {final_bal:,.2f} USDT")
    print(f"누적 수익률: {total_roi:,.2f} %")
    print(f"최대 낙폭 (MDD): {mdd:.2f} %")
    print(f"총 거래 횟수: {len(trades)} 회")
    print(f"평균 승률: {win_rate:.2f} %")
    print(f"평균 거래 수익률: {avg_roi:.2f} %")
    print(f"최대 단일 익절: {max_win:.2f} %")
    print(f"최대 단일 손절: {max_loss:.2f} %")
    print("="*50)

    # 자산 곡선 저장 (텍스트 기반 확인용)
    if len(equity_curve) > 100:
        step = len(equity_curve) // 20
        print("\n[자산 성장 추이]")
        for i in range(0, len(equity_curve), step):
            print(f"- 시점 {i:5d}: ${equity_curve[i]:15,.2f}")
    
    # 거래 로그 요약
    if len(trades) > 0:
        print("\n[최근 5회 거래 로그]")
        for t in trades[-5:]:
            print(f"- {t['date']}: {t['type']} ({t['reason']}) ROI: {t['roi']:.2f}% | 잔고: ${t['balance']:,.2f}")

if __name__ == "__main__":
    run_live_simulation()
