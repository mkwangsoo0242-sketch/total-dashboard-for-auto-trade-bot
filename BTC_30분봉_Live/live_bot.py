import ccxt
import pandas as pd
import time
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from strategy_30m import Strategy30m

# BaseBot 임포트를 위한 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bots.base_bot import BaseBot

# .env 파일에서 설정 로드 (중앙 집중식)
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path)

class BinanceLiveBot(BaseBot):
    def execute_logic(self):
        # BaseBot requires this, but we use run() loop.
        pass

    def __init__(self):
        super().__init__(name="Bot_30M", interval="30m")
        
        # 모드 설정 (paper/live) - 가장 먼저 설정
        self.mode = os.getenv('TRADING_MODE', 'paper').lower()

        # 가상 거래 상태 변수 (Real-time Simulation)
        self.paper_balance = 100.0  # 초기 자본 100 USDT
        self.paper_pos_size = 0.0     # 코인 수량 (양수: 롱, 음수: 숏)
        self.paper_entry_price = 0.0  # 평단가
        
        # 30분봉 전용 키 우선 적용, 없으면 공용 키 사용
        self.api_key = os.getenv('BINANCE_API_KEY_30M') or os.getenv('BINANCE_API_KEY')
        self.api_secret = os.getenv('BINANCE_SECRET_30M') or os.getenv('BINANCE_SECRET_KEY') or os.getenv('BINANCE_SECRET')
        self.symbol = 'BTC/USDT'
        self.timeframe = '30m'
        
        # 바이낸스 선물 거래소 초기화
        exchange_config = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'options': {'defaultType': 'future'},
            'enableRateLimit': True,
        }
        if self.mode == 'paper':
            exchange_config['apiKey'] = None
            exchange_config['secret'] = None
            
        self.exchange = ccxt.binance(exchange_config)
        
        # 전략 인스턴스 초기화 (실거래 모드)
        self.strat = Strategy30m(initial_leverage=10, mode='extreme_growth')
        
        # 상태 관리 변수
        self.current_position = None # 'long', 'short', None
        self.entry_price = 0
        self.total_position_size = 0
        self.stop_price = 0
        self.peak_price = 0
        self.trade_leverage = 10
        self.partial_hits = {'0': False, '1': False, '2': False}

    def log(self, message):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{now}] [{self.mode.upper()}] {message}")

    def fetch_ohlcv(self, limit=1500):
        """실시간 OHLCV 데이터를 가져와 데이터프레임으로 변환"""
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=limit)
        
        # 차트용 데이터 저장 (최근 100개만)
        self.recent_candles = [
            {'x': item[0], 'y': [item[1], item[2], item[3], item[4]]}
            for item in ohlcv[-100:]
        ]
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df

    def get_balance(self):
        """계좌 잔고 조회 (Paper 모드 시 시뮬레이션 잔고)"""
        if self.mode == 'paper':
            return self.paper_balance
        
        balance = self.exchange.fetch_balance()
        return float(balance['total']['USDT'])

    def execute_order(self, side, amount, order_type='market', price=None):
        """주문 실행 (Paper 모드: 실제 가격 기반 시뮬레이션)"""
        if self.mode == 'paper':
            try:
                # 1. 현재가 조회 (실제 시장 데이터)
                ticker = self.exchange.fetch_ticker(self.symbol)
                current_price = float(ticker['last'])
                if price: current_price = float(price)
            except:
                current_price = float(self.fetch_ohlcv(limit=1).iloc[-1]['close'])

            # 수수료 가정 (0.05%)
            fee_rate = 0.0005
            trade_value = current_price * amount
            fee = trade_value * fee_rate
            
            self.paper_balance -= fee
            
            # 포지션 업데이트 로직
            if side == 'buy':
                # 숏 포지션 청산 or 롱 진입
                if self.paper_pos_size < 0: # 숏 청산
                    cover_amt = min(amount, abs(self.paper_pos_size))
                    # 숏 수익 = (진입가 - 현재가) * 수량
                    pnl = (self.paper_entry_price - current_price) * cover_amt
                    self.paper_balance += pnl
                    self.paper_pos_size += cover_amt
                    if abs(self.paper_pos_size) < 1e-8: 
                        self.paper_pos_size = 0.0
                        self.paper_entry_price = 0.0
                    
                    if amount > cover_amt: # 청산 후 남은 물량 롱 진입
                        rem_amt = amount - cover_amt
                        self.paper_pos_size += rem_amt
                        self.paper_entry_price = current_price
                        
                else: # 롱 진입/추가
                    if self.paper_pos_size == 0:
                        self.paper_entry_price = current_price
                        self.paper_pos_size += amount
                    else:
                        total_val = (self.paper_pos_size * self.paper_entry_price) + (amount * current_price)
                        self.paper_pos_size += amount
                        self.paper_entry_price = total_val / self.paper_pos_size
                    
            elif side == 'sell':
                # 롱 포지션 청산 or 숏 진입
                if self.paper_pos_size > 0: # 롱 청산
                    sell_amt = min(amount, self.paper_pos_size)
                    # 롱 수익 = (현재가 - 진입가) * 수량
                    pnl = (current_price - self.paper_entry_price) * sell_amt
                    self.paper_balance += pnl
                    self.paper_pos_size -= sell_amt
                    if abs(self.paper_pos_size) < 1e-8:
                        self.paper_pos_size = 0.0
                        self.paper_entry_price = 0.0
                    
                    if amount > sell_amt: # 청산 후 남은 물량 숏 진입
                        rem_amt = amount - sell_amt
                        self.paper_pos_size -= rem_amt
                        self.paper_entry_price = current_price
                else: # 숏 진입/추가
                    if self.paper_pos_size == 0:
                        self.paper_entry_price = current_price
                        self.paper_pos_size -= amount
                    else:
                        total_val = (abs(self.paper_pos_size) * self.paper_entry_price) + (amount * current_price)
                        self.paper_pos_size -= amount
                        self.paper_entry_price = total_val / abs(self.paper_pos_size)

            self.log(f"🧪 [Paper] 시뮬레이션 체결: {side.upper()} {amount} @ {current_price} | 잔고: {self.paper_balance:.2f} | 포지션: {self.paper_pos_size:.4f}")
            return {'id': 'paper_order', 'status': 'closed', 'filled': amount, 'average': current_price}

        try:
            params = {}
            if order_type == 'market':
                order = self.exchange.create_order(self.symbol, 'market', side, amount)
            else:
                order = self.exchange.create_order(self.symbol, 'limit', side, amount, price)
            return order
        except Exception as e:
            self.log(f"주문 실행 오류: {e}")
            return None

    def sync_position(self):
        """거래소의 실제 포지션과 로컬 상태 동기화"""
        if self.mode == 'paper':
            if self.paper_pos_size > 1e-8:
                self.current_position = 'long'
                self.total_position_size = self.paper_pos_size
                self.entry_price = self.paper_entry_price
            elif self.paper_pos_size < -1e-8:
                self.current_position = 'short'
                self.total_position_size = abs(self.paper_pos_size)
                self.entry_price = self.paper_entry_price
            else:
                self.current_position = None
                self.total_position_size = 0
                self.entry_price = 0
            
            # self.log(f"포지션 동기화 (Paper): {self.current_position} (Size: {self.total_position_size:.4f}, Entry: {self.entry_price:.2f})")
            return

        positions = self.exchange.fetch_positions([self.symbol])
        for pos in positions:
            if pos['symbol'] == 'BTCUSDT':
                size = float(pos['contracts'])
                if size > 0:
                    self.current_position = 'long'
                    self.total_position_size = size
                    self.entry_price = float(pos['entryPrice'])
                elif size < 0:
                    self.current_position = 'short'
                    self.total_position_size = abs(size)
                    self.entry_price = float(pos['entryPrice'])
                else:
                    self.current_position = None
                    self.total_position_size = 0
                    self.entry_price = 0
        self.log(f"포지션 동기화 완료: {self.current_position} (Size: {self.total_position_size})")

    def set_leverage(self, leverage):
        """레버리지 설정"""
        if self.mode == 'paper':
            return

        try:
            self.exchange.set_leverage(leverage, self.symbol)
            self.log(f"레버리지 {leverage}x 설정 완료")
        except Exception as e:
            self.log(f"레버리지 설정 오류: {e}")

    def run(self):
        self.is_running = True
        self.log("BTC 30M 자동매매 봇 시작 (Adaptive Strategy)")
        self.sync_position()
        
        # 초기 레버리지 설정
        self.set_leverage(self.trade_leverage)
        
        while self.is_running:
            try:
                from datetime import datetime
                self.last_run = datetime.now()
                
                # 1. 데이터 업데이트
                df = self.fetch_ohlcv()
                df_with_ind = self.strat.populate_indicators(df)
                
                # 실시간 신호 및 파라미터 가져오기
                signal_data = self.strat.get_current_signal(df_with_ind)
                curr = df_with_ind.iloc[-1]
                current_price = curr['close']
                balance = self.get_balance()
                
                # 대시보드 데이터 업데이트
                self.current_balance = balance
                self.status = "신호 대기 중" if self.current_position is None else f"{self.current_position.upper()} 유지 중"
                self.balance_history.append(balance)
                if len(self.balance_history) > self.max_history:
                    self.balance_history.pop(0)
                
                self.log(f"현재가: {current_price:.2f} | 포지션: {self.current_position} | 잔고: {balance:.2f} USDT")

                # 2. 포지션이 없는 경우: 진입 판단
                if self.current_position is None:
                    action = signal_data['action']
                    if action in ['long', 'short']:
                        self.trade_leverage = signal_data['leverage']
                        self.set_leverage(int(self.trade_leverage))
                        
                        # 수량 계산 (Risk-based)
                        risk_pct = signal_data['risk_pct']
                        stop_atr = signal_data['stop_atr']
                        
                        # 진입 및 초기 손절가 설정
                        self.entry_price = current_price
                        if action == 'long':
                            self.stop_price = self.entry_price - (curr['atr'] * stop_atr)
                            side = 'buy'
                        else:
                            self.stop_price = self.entry_price + (curr['atr'] * stop_atr)
                            side = 'sell'
                        
                        # 리스크 기반 수량 계산
                        stop_dist_pct = abs(self.entry_price - self.stop_price) / self.entry_price
                        if stop_dist_pct < 0.005: stop_dist_pct = 0.005
                        
                        # Margin = Risk / (Leverage * StopDist)
                        # PositionValue = Margin * Leverage = Risk / StopDist
                        pos_value = (balance * risk_pct) / stop_dist_pct
                        amount = pos_value / self.entry_price
                        
                        # 최소 주문 수량 및 잔고 확인 등 추가 로직 필요 (여기선 간소화)
                        self.log(f"{action} 진입 시도: 가격 {self.entry_price}, 수량 {amount:.4f}, 레버리지 {self.trade_leverage:.1f}")
                        
                        order = self.execute_order(side, amount)
                        if order:
                            self.current_position = action
                            self.total_position_size = amount
                            self.peak_price = self.entry_price
                            self.partial_hits = {'0': False, '1': False, '2': False}
                            self.log(f"{action} 진입 완료. 초기 손절가: {self.stop_price:.2f}")

                # 3. 포지션이 있는 경우: 익절/손절/트레일링 판단
                else:
                    # ROI 계산
                    if self.current_position == 'long':
                        roi_unleveraged = (current_price - self.entry_price) / self.entry_price
                        is_exit_signal = current_price < signal_data['donchian_low']
                        
                        # 트레일링 스탑 (Ratchet)
                        if current_price > self.peak_price:
                            self.peak_price = current_price
                            roi_leveraged = roi_unleveraged * self.trade_leverage
                            
                            # strategy.py의 Ratchet 로직 반영
                            if self.strat.mode == 'extreme_growth':
                                if roi_leveraged > 0.08: self.stop_price = max(self.stop_price, self.entry_price * 1.002)
                                
                                trail_tightness = 0.98 if not signal_data['is_strong_bull'] else 0.94
                                trail_mid = 0.96 if not signal_data['is_strong_bull'] else 0.92
                                trail_loose = 0.94 if not signal_data['is_strong_bull'] else 0.90

                                if roi_leveraged > 4.0: self.stop_price = max(self.stop_price, self.peak_price * trail_loose)
                                elif roi_leveraged > 2.0: self.stop_price = max(self.stop_price, self.peak_price * trail_mid)
                                elif roi_leveraged > 1.0: self.stop_price = max(self.stop_price, self.peak_price * trail_tightness)
                                elif roi_leveraged > 0.4: self.stop_price = max(self.stop_price, self.entry_price * 1.05)
                        
                        # 손절 체크
                        if current_price <= self.stop_price or is_exit_signal:
                            reason = "stop_loss" if current_price <= self.stop_price else "signal_exit"
                            self.log(f"롱 종료 ({reason}): 가격 {current_price}")
                            self.execute_order('sell', self.total_position_size)
                            self.current_position = None
                            continue

                        # 분할 익절 체크 (Long)
                        if self.strat.mode == 'extreme_growth':
                            p_ratio = 0.08 if signal_data['is_strong_bull'] else 0.15
                            leveraged_roi = roi_unleveraged * self.trade_leverage
                            
                            # Target 1: 50% ROI
                            if leveraged_roi > 0.5 and not self.partial_hits['0']:
                                sell_amt = self.total_position_size * p_ratio
                                self.log(f"롱 1차 분할 익절 (50% ROI): {sell_amt:.4f}")
                                if self.execute_order('sell', sell_amt):
                                    self.partial_hits['0'] = True
                                    self.sync_position()

                            # Target 2: 120% ROI
                            if leveraged_roi > 1.2 and not self.partial_hits['1']:
                                sell_amt = self.total_position_size * p_ratio
                                self.log(f"롱 2차 분할 익절 (120% ROI): {sell_amt:.4f}")
                                if self.execute_order('sell', sell_amt):
                                    self.partial_hits['1'] = True
                                    self.stop_price = max(self.stop_price, self.entry_price * 1.01)
                                    self.sync_position()

                            # Target 3: 300% ROI
                            if leveraged_roi > 3.0 and not self.partial_hits['2']:
                                p_ratio_3 = 0.1 if signal_data['is_strong_bull'] else 0.2
                                sell_amt = self.total_position_size * p_ratio_3
                                self.log(f"롱 3차 분할 익절 (300% ROI): {sell_amt:.4f}")
                                if self.execute_order('sell', sell_amt):
                                    self.partial_hits['2'] = True
                                    self.stop_price = max(self.stop_price, self.entry_price * (1 + roi_unleveraged * 0.7))
                                    self.sync_position()
                    
                    elif self.current_position == 'short':
                        roi_unleveraged = (self.entry_price - current_price) / self.entry_price
                        is_exit_signal = current_price > curr['donchian_high'] # strategy.py 참조
                        
                        # 트레일링 스탑 (Ratchet)
                        if current_price < self.peak_price: # Short에서는 peak가 저점
                            self.peak_price = current_price
                            roi_leveraged = roi_unleveraged * self.trade_leverage
                            
                            if self.strat.mode == 'extreme_growth':
                                if roi_leveraged > 0.08: self.stop_price = min(self.stop_price, self.entry_price * 0.998)
                                if roi_leveraged > 4.0: self.stop_price = min(self.stop_price, self.peak_price * 1.05)
                                elif roi_leveraged > 2.0: self.stop_price = min(self.stop_price, self.peak_price * 1.03)
                                elif roi_leveraged > 1.0: self.stop_price = min(self.stop_price, self.peak_price * 1.02)
                                elif roi_leveraged > 0.4: self.stop_price = min(self.stop_price, self.entry_price * 0.95)
                        
                        # 손절 체크
                        if current_price >= self.stop_price or is_exit_signal:
                            reason = "stop_loss" if current_price >= self.stop_price else "signal_exit"
                            self.log(f"숏 종료 ({reason}): 가격 {current_price}")
                            self.execute_order('buy', self.total_position_size)
                            self.current_position = None
                            continue

                        # 분할 익절 체크 (Short)
                        if self.strat.mode == 'extreme_growth':
                            leveraged_roi = roi_unleveraged * self.trade_leverage
                            
                            # Target 1: 40% ROI
                            if leveraged_roi > 0.4 and not self.partial_hits['0']:
                                sell_amt = self.total_position_size * 0.15
                                self.log(f"숏 1차 분할 익절 (40% ROI): {sell_amt:.4f}")
                                if self.execute_order('buy', sell_amt):
                                    self.partial_hits['0'] = True
                                    self.sync_position()

                            # Target 2: 100% ROI
                            if leveraged_roi > 1.0 and not self.partial_hits['1']:
                                sell_amt = self.total_position_size * 0.15
                                self.log(f"숏 2차 분할 익절 (100% ROI): {sell_amt:.4f}")
                                if self.execute_order('buy', sell_amt):
                                    self.partial_hits['1'] = True
                                    self.stop_price = min(self.stop_price, self.entry_price * 0.99)
                                    self.sync_position()

                            # Target 3: 250% ROI
                            if leveraged_roi > 2.5 and not self.partial_hits['2']:
                                sell_amt = self.total_position_size * 0.2
                                self.log(f"숏 3차 분할 익절 (250% ROI): {sell_amt:.4f}")
                                if self.execute_order('buy', sell_amt):
                                    self.partial_hits['2'] = True
                                    self.stop_price = min(self.stop_price, self.entry_price * (1 - roi_unleveraged * 0.7))
                                    self.sync_position()

                # 4. 대기 (30분봉 전략이므로 1분마다 체크)
                self.wait_while_running(60)
                
            except Exception as e:
                self.log(f"루프 실행 중 오류 발생: {e}")
                self.wait_while_running(30)
                
        self.status = "Stopped"
        self.log("30M Bot Stopped Loop.")

    def wait_while_running(self, seconds):
        for _ in range(seconds):
            if not self.is_running:
                return
            time.sleep(1)
                
if __name__ == "__main__":
    bot = BinanceLiveBot()
    bot.run()
