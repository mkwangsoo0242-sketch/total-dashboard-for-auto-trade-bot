
import pandas as pd
import sys
import os

# 현재 폴더 경로 추가 (strategy.py 로드)
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from strategy import Strategy30m, MultiStrategySystem
except ImportError as e:
    print(f"❌ Strategy import 실패: {e}")
    sys.exit(1)

def run():
    print("🚀 [30분봉] 정밀 백테스트 시작 (MultiStrategySystem)...")
    
    # 데이터 로드
    data_path = "../portfolio_data.csv"
    if not os.path.exists(data_path):
        data_path = "../../portfolio_data.csv"
        
    if not os.path.exists(data_path):
        print(f"❌ 데이터 파일을 찾을 수 없습니다: {data_path}")
        return

    df = pd.read_csv(data_path)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC')
    df = df.set_index('datetime').sort_index()
    
    # 30분봉 리샘플링
    df_30m = df.resample('30min').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()
    
    # Strategy 초기화 (5배 레버리지 - 안정형)
    strategy = MultiStrategySystem(leverage=5) 
    
    print("   📊 전략 지표 계산 중...")
    try:
        strategy.populate_indicators(df_30m)
    except Exception as e:
        print(f"   ⚠️ 지표 계산 오류: {e}")
        return

    print("   ⚔️ 매매 시뮬레이션 (연도별 복리)...")
    
    years = sorted(list(set(df_30m.index.year)))
    
    # 결과를 변수로 받음
    # MultiStrategySystem.backtest_compounding은 보통 총 수익률 등을 리턴하거나 내부에서 출력함
    # 여기서는 내부 출력이 안 나오니, 강제로 total_roi 등을 계산해서 찍어봄
    
    results = strategy.backtest_compounding(df_30m, years, initial_balance=100000)
    
    if results:
         # 만약 results가 딕셔너리면 출력
        print("\n===========================================")
        print(f"📊 30분봉 최종 성과 리포트")
        print("===========================================")
        if isinstance(results, dict):
            for k, v in results.items():
                print(f"   {k}: {v}")
        else:
             print(f"   결과: {results}")
    else:
        # 리턴값이 없으면 strategy 내부 상태를 찍어봄 (만약 저장되어 있다면)
        pass

if __name__ == "__main__":
    run()
