import pandas as pd
import numpy as np
import json
import logging
from datetime import datetime, timedelta, timezone
import itertools
import os
import sys

# 현재 디렉토리를 path에 추가하여 임포트 가능하게 함
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from strategy import AdaptiveStrategy, AdaptiveConfig, fetch_klines
    from bybit_client import BybitClient
    import config as cfg
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(current_dir, "auto_optimizer.log")),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('auto_optimizer')

DYNAMIC_CONFIG_PATH = os.path.join(current_dir, 'dynamic_config.json')

def fetch_recent_data(client: BybitClient, symbol: str, interval: str, days: int = 60) -> pd.DataFrame:
    """최근 데이터를 가져와서 DataFrame으로 반환"""
    logger.info(f"Fetching last {days} days of data for {symbol} ({interval}m)...")
    
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)
    
    try:
        df = fetch_klines(symbol, interval, start_ms, end_ms)
        return df
    except Exception as e:
        logger.error(f"Error fetching klines: {e}")
        return pd.DataFrame()

def run_single_backtest(df, p):
    """단일 백테스트 실행"""
    config = AdaptiveConfig(
        leverage=p['leverage'],
        adx_trending_min=p['adx_trending_min'],
        adx_ranging_max=p['adx_ranging_max'],
        trend_sl_atr=p['trend_sl_atr'],
        range_sl_atr=p['range_sl_atr'],
        session_start_hour=p['session_start_hour'],
        session_end_hour=p['session_end_hour']
    )
    strategy = AdaptiveStrategy(config)
    result = strategy.backtest(df)
    
    # 평가 점수 계산 (수익률 / (MDD + 0.1))
    score = result['total_return'] / (result['max_drawdown'] + 0.1)
    
    return {
        'params': p,
        'score': score,
        'total_return': result['total_return'],
        'max_drawdown': result['max_drawdown'],
        'win_rate': result['win_rate']
    }

def optimize():
    """최적화 메인 프로세스"""
    logger.info("Starting Auto Optimization Process...")
    
    # API 키가 없는 경우 config에서 직접 가져오기 시도
    api_key = cfg.BYBIT_API_KEY
    api_secret = cfg.BYBIT_API_SECRET
    
    client = BybitClient(api_key, api_secret, testnet=cfg.USE_TESTNET)
    
    # 데이터 수집 (최근 60일)
    df = fetch_recent_data(client, cfg.SYMBOL, cfg.TIMEFRAME, days=60)
    
    if df.empty:
        logger.error("No data fetched. Optimization aborted.")
        return
    
    logger.info(f"Data fetched: {len(df)} rows.")

    # 파라미터 그리드 설정 (현실적인 범위로 축소하여 속도 향상)
    param_grid = {
        'leverage': [1.0, 2.0, 3.0],
        'adx_trending_min': [25, 30],
        'adx_ranging_max': [15, 20],
        'trend_sl_atr': [1.5, 2.0, 2.5],
        'range_sl_atr': [1.0, 1.5, 2.0],
        'session_start_hour': [0],
        'session_end_hour': [23]
    }
    
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    logger.info(f"Testing {len(combinations)} combinations...")
    
    results = []
    for i, p in enumerate(combinations):
        if i % 10 == 0:
            logger.info(f"Progress: {i}/{len(combinations)}")
        res = run_single_backtest(df, p)
        results.append(res)
        
    if not results:
        logger.error("No results generated.")
        return

    best_result = max(results, key=lambda x: x['score'])
    
    logger.info("=" * 50)
    logger.info("BEST PARAMETERS FOUND")
    logger.info(f"Score: {best_result['score']:.4f}")
    logger.info(f"Params: {best_result['params']}")
    logger.info(f"Return: {best_result['total_return']*100:.2f}%")
    logger.info(f"MDD: {best_result['max_drawdown']*100:.2f}%")
    logger.info("=" * 50)
    
    # 결과 저장
    existing_config = {}
    if os.path.exists(DYNAMIC_CONFIG_PATH):
        try:
            with open(DYNAMIC_CONFIG_PATH, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
        except Exception as e:
            logger.error(f"Error loading existing config: {e}")

    now_dt = datetime.now()
    output = {
        'updated_at': now_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'last_optimized_date': now_dt.strftime('%Y-%m-%d'),
        'parameters': best_result['params'],
        'performance': {
            'recent_return': float(best_result['total_return']),
            'recent_mdd': float(best_result['max_drawdown']),
            'win_rate': float(best_result['win_rate']),
            'score': float(best_result['score'])
        }
    }
    
    # 기존 설정 중 보존해야 할 필드가 있다면 병합 (현재는 last_optimized_date를 새로 생성하므로 생략 가능하지만 구조상 유지)
    # for key, value in existing_config.items():
    #     if key not in output:
    #         output[key] = value

    with open(DYNAMIC_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4)
        
    logger.info(f"Dynamic config saved to {DYNAMIC_CONFIG_PATH}")

if __name__ == "__main__":
    try:
        optimize()
    except Exception as e:
        logger.error(f"Critical error in optimizer: {e}", exc_info=True)
