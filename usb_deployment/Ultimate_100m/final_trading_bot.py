"""
🎯 최종 전략 - 다중 ML 모델 Paper Trading 봇
Short + Long + Regime 모델 사용

백테스트 결과:
- 5년간 모든 년도 수익
- 10만원 → 7.6억원 (7,617배)
- MDD 8.8%, 승률 80.2%
"""
import ccxt
import pandas as pd
import numpy as np
import joblib
import os
import time
import logging
import json
from datetime import datetime
from dotenv import load_dotenv
from strategy import add_indicators

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading.log"),
        logging.StreamHandler()
    ]
)

TRADING_COSTS = {
    'taker_fee': 0.0004,
    'slippage': 0.0003,
    'funding_rate': 0.0001,
}

# 레짐별 설정
REGIME_SETTINGS = {
    0: {  # SIDEWAYS
        'name': 'SIDEWAYS',
        'skip': True,
    },
    1: {  # BULL
        'name': 'BULL',
        'direction': 'long',
        'leverage': 12,
        'risk': 0.04,
        'sl_mult': 1.0,
        'tp_mult': 4.0,
        'threshold': 0.55,
    },
    2: {  # BEAR
        'name': 'BEAR',
        'direction': 'short',
        'leverage': 8,
        'risk': 0.03,
        'sl_mult': 1.0,
        'tp_mult': 3.0,
        'threshold': 0.55,
    },
}


class FinalTradingBot:
    """최종 다중 ML 모델 트레이딩 봇"""
    
    def __init__(self, initial_balance=100000):
        load_dotenv()
        
        # 모델 로드
        logging.info("🤖 ML 모델 로딩...")
        self.short_model_data = joblib.load('short_model.pkl')
        self.long_model_data = joblib.load('long_model.pkl')
        self.regime_model_data = joblib.load('regime_model.pkl')
        
        self.short_model = self.short_model_data['model']
        self.long_model = self.long_model_data['model']
        self.regime_model = self.regime_model_data['model']
        
        logging.info(f"   Short 모델 정확도: {self.short_model_data['accuracy']*100:.1f}%")
        logging.info(f"   Long 모델 정확도: {self.long_model_data['accuracy']*100:.1f}%")
        logging.info(f"   Regime 모델 정확도: {self.regime_model_data['accuracy']*100:.1f}%")
        
        # 거래소 초기화
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        self.symbol = 'BTC/USDT'
        self.timeframe = '1h'
        
        # 상태
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.position = 0
        self.entry_price = 0
        self.sl_price = 0
        self.tp_price = 0
        self.entry_regime = None
        self.trades = []
        self.max_balance = initial_balance
        self.max_drawdown = 0
        self.total_fees = 0
        
        self.consecutive_losses = 0
        self.rest_until = 0
        
        # 상태 파일
        self.state_file = 'trading_state.json'
        self.load_state()
        
    def save_state(self):
        state = {
            'balance': self.balance,
            'position': self.position,
            'entry_price': self.entry_price,
            'sl_price': self.sl_price,
            'tp_price': self.tp_price,
            'entry_regime': self.entry_regime,
            'trades': self.trades[-50:],
            'max_balance': self.max_balance,
            'max_drawdown': self.max_drawdown,
            'total_fees': self.total_fees,
            'consecutive_losses': self.consecutive_losses,
            'last_update': datetime.now().isoformat()
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2, default=str)
    
    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                self.balance = state.get('balance', self.initial_balance)
                self.position = state.get('position', 0)
                self.entry_price = state.get('entry_price', 0)
                self.sl_price = state.get('sl_price', 0)
                self.tp_price = state.get('tp_price', 0)
                self.entry_regime = state.get('entry_regime', None)
                self.trades = state.get('trades', [])
                self.max_balance = state.get('max_balance', self.initial_balance)
                self.max_drawdown = state.get('max_drawdown', 0)
                self.total_fees = state.get('total_fees', 0)
                logging.info(f"📂 상태 복원: 잔고 {self.balance:,.0f}원")
            except Exception as e:
                logging.error(f"상태 복원 실패: {e}")
    
    def fetch_data(self, limit=250):
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # 지표 추가
            df = add_indicators(df)
            
            # 추가 피처
            df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
            df['dist_ema60'] = (df['close'] - df['ema_60']) / df['ema_60']
            df['rsi_change'] = df['rsi'].diff()
            df['adx_change'] = df['adx'].diff()
            df['vol_change'] = df['volume'].pct_change()
            df['stoch_diff'] = df['stoch_k'] - df['stoch_d']
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
            df['vol_ratio'] = df['volume'] / df['vol_ma20']
            df['ema_slope'] = df['ema_20'].pct_change() * 100
            df['ema_200'] = df['close'].ewm(span=200).mean()
            df['dist_ema200'] = (df['close'] - df['ema_200']) / df['ema_200']
            
            return df
        except Exception as e:
            logging.error(f"데이터 조회 실패: {e}")
            return None
    
    def get_features(self, row, feature_list):
        features = {}
        for f in feature_list:
            val = row.get(f, 0)
            features[f] = val if not pd.isna(val) else 0
        return pd.DataFrame([features])
    
    def predict_regime(self, row):
        try:
            features = self.get_features(row, self.regime_model_data['features'])
            return int(self.regime_model.predict(features)[0])
        except:
            return 0
    
    def predict_short_prob(self, row):
        try:
            features = self.get_features(row, self.short_model_data['features'])
            return self.short_model.predict_proba(features)[0][1]
        except:
            return 0.5
    
    def predict_long_prob(self, row):
        try:
            features = self.get_features(row, self.long_model_data['features'])
            return self.long_model.predict_proba(features)[0][1]
        except:
            return 0.5
    
    def check_exit(self, current_price, high, low):
        if self.position == 0:
            return
        
        is_long = self.position > 0
        exit_price = None
        exit_reason = None
        
        if is_long:
            if low <= self.sl_price:
                exit_price = self.sl_price * (1 - TRADING_COSTS['slippage'])
                exit_reason = 'SL'
            elif high >= self.tp_price:
                exit_price = self.tp_price * (1 - TRADING_COSTS['slippage'])
                exit_reason = 'TP'
        else:
            if high >= self.sl_price:
                exit_price = self.sl_price * (1 + TRADING_COSTS['slippage'])
                exit_reason = 'SL'
            elif low <= self.tp_price:
                exit_price = self.tp_price * (1 + TRADING_COSTS['slippage'])
                exit_reason = 'TP'
        
        if exit_price:
            if is_long:
                gross_pnl = (exit_price - self.entry_price) * self.position
            else:
                gross_pnl = (self.entry_price - exit_price) * abs(self.position)
            
            exit_fee = abs(self.position) * exit_price * TRADING_COSTS['taker_fee']
            net_pnl = gross_pnl - exit_fee
            self.balance += net_pnl
            self.total_fees += exit_fee
            
            logging.info(f"📊 {'✅ TP' if exit_reason == 'TP' else '❌ SL'} 청산!")
            logging.info(f"   진입: ${self.entry_price:,.2f} → 청산: ${exit_price:,.2f}")
            logging.info(f"   PnL: {net_pnl:+,.0f}원 | 새 잔고: {self.balance:,.0f}원")
            
            if net_pnl < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0
            
            self.trades.append({
                'type': exit_reason,
                'pnl': net_pnl,
                'regime': self.entry_regime,
                'time': datetime.now().isoformat()
            })
            
            self.position = 0
            self.entry_price = 0
            self.sl_price = 0
            self.tp_price = 0
            self.entry_regime = None
            
            self.save_state()
    
    def execute_entry(self, signal, price, atr, settings, regime):
        leverage = settings['leverage']
        risk = settings['risk']
        sl_mult = settings['sl_mult']
        tp_mult = settings['tp_mult']
        
        # DD 기반 조절
        current_dd = (self.max_balance - self.balance) / self.max_balance if self.max_balance > 0 else 0
        dd_mult = 1.0
        if current_dd > 0.15:
            dd_mult = 0.3
        elif current_dd > 0.08:
            dd_mult = 0.6
        
        leverage *= dd_mult
        risk *= dd_mult
        
        if leverage <= 0 or risk <= 0:
            return
        
        entry_price = price * (1 + TRADING_COSTS['slippage'] if signal == 'long' else 1 - TRADING_COSTS['slippage'])
        
        sl_distance = atr * sl_mult
        sl_pct = sl_distance / price
        if sl_pct <= 0:
            return
        
        risk_amt = self.balance * risk
        target_notional = risk_amt / sl_pct
        max_notional = self.balance * leverage
        pos_size = min(target_notional, max_notional)
        
        entry_fee = pos_size * TRADING_COSTS['taker_fee']
        self.balance -= entry_fee
        self.total_fees += entry_fee
        
        quantity = (pos_size - entry_fee) / entry_price
        self.position = quantity if signal == 'long' else -quantity
        self.entry_price = entry_price
        self.entry_regime = regime
        
        if signal == 'long':
            self.sl_price = entry_price - (atr * sl_mult)
            self.tp_price = entry_price + (atr * tp_mult)
        else:
            self.sl_price = entry_price + (atr * sl_mult)
            self.tp_price = entry_price - (atr * tp_mult)
        
        logging.info(f"📈 {'LONG' if signal == 'long' else 'SHORT'} 진입!")
        logging.info(f"   레짐: {REGIME_SETTINGS[regime]['name']}")
        logging.info(f"   진입가: ${entry_price:,.2f} | 수량: {abs(quantity):.6f} BTC")
        logging.info(f"   SL: ${self.sl_price:,.2f} | TP: ${self.tp_price:,.2f}")
        
        self.save_state()
    
    def print_status(self):
        roi = (self.balance - self.initial_balance) / self.initial_balance * 100
        
        win_trades = len([t for t in self.trades if t.get('pnl', 0) > 0])
        loss_trades = len([t for t in self.trades if t.get('pnl', 0) <= 0])
        total_trades = win_trades + loss_trades
        win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
        
        print("\n" + "=" * 60)
        print(f"🎯 최종 전략 Paper Trading (다중 ML 모델)")
        print("=" * 60)
        print(f"💰 초기: {self.initial_balance:,.0f}원 → 현재: {self.balance:,.0f}원 ({roi:+.2f}%)")
        print(f"📉 MDD: {self.max_drawdown*100:.2f}%")
        print(f"📈 거래: {total_trades}건 (승: {win_trades}, 패: {loss_trades}, 승률: {win_rate:.1f}%)")
        
        if self.position != 0:
            print(f"\n🔥 포지션: {'LONG' if self.position > 0 else 'SHORT'}")
            print(f"   진입가: ${self.entry_price:,.2f}")
            print(f"   SL: ${self.sl_price:,.2f} | TP: ${self.tp_price:,.2f}")
        else:
            print(f"\n⏳ 포지션 없음 - 신호 대기 중")
        
        print("=" * 60 + "\n")
    
    def run(self):
        logging.info("🚀 최종 전략 Paper Trading 시작!")
        logging.info(f"   초기 잔고: {self.initial_balance:,.0f}원")
        
        while True:
            try:
                # 연속 손실 휴식
                if self.consecutive_losses >= 3:
                    logging.warning(f"⏸️ 연속 {self.consecutive_losses}회 손실 - 1시간 휴식")
                    self.consecutive_losses = 0
                    time.sleep(3600)
                    continue
                
                # 데이터 가져오기
                df = self.fetch_data()
                if df is None:
                    time.sleep(60)
                    continue
                
                current = df.iloc[-1]
                price = current['close']
                
                # 상태 업데이트
                if self.balance > self.max_balance:
                    self.max_balance = self.balance
                current_dd = (self.max_balance - self.balance) / self.max_balance
                if current_dd > self.max_drawdown:
                    self.max_drawdown = current_dd
                
                # 포지션 있으면 청산 체크
                if self.position != 0:
                    self.check_exit(price, current['high'], current['low'])
                
                # 포지션 없으면 진입 체크
                if self.position == 0:
                    regime = self.predict_regime(current)
                    settings = REGIME_SETTINGS.get(regime, {'skip': True})
                    
                    if not settings.get('skip'):
                        direction = settings['direction']
                        threshold = settings['threshold']
                        
                        if direction == 'long':
                            prob = self.predict_long_prob(current)
                            if prob > threshold:
                                atr = current['atr'] if not pd.isna(current['atr']) else price * 0.01
                                if atr > 0:
                                    logging.info(f"🔍 Long 신호! (확률: {prob:.2%}, 레짐: {settings['name']})")
                                    self.execute_entry('long', price, atr, settings, regime)
                        else:
                            prob = self.predict_short_prob(current)
                            if prob > threshold:
                                atr = current['atr'] if not pd.isna(current['atr']) else price * 0.01
                                if atr > 0:
                                    logging.info(f"🔍 Short 신호! (확률: {prob:.2%}, 레짐: {settings['name']})")
                                    self.execute_entry('short', price, atr, settings, regime)
                
                # 상태 출력
                self.print_status()
                
                # 목표 체크
                if self.balance >= 100000000:
                    logging.info("🎉🎉🎉 1억 달성! 🎉🎉🎉")
                    break
                
                if self.balance <= 0:
                    logging.error("💥 파산!")
                    break
                
                # 1시간 대기
                time.sleep(3600)
                
            except KeyboardInterrupt:
                logging.info("⏹️ 봇 중지...")
                self.save_state()
                break
            except Exception as e:
                logging.error(f"오류: {e}")
                time.sleep(60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Final ML Trading Bot')
    parser.add_argument('--balance', type=int, default=100000, help='초기 잔고')
    args = parser.parse_args()
    
    bot = FinalTradingBot(initial_balance=args.balance)
    bot.run()


if __name__ == "__main__":
    main()
