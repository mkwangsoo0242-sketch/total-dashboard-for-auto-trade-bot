"""
바이비트 실거래 봇 (Integrated Adaptive Strategy + ML Filter)
"""

import time
import logging
import pandas as pd
import numpy as np
import json
import subprocess
import os
import sys
import joblib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from bybit_client import BybitClient
import config as cfg
from strategy_1h import add_indicators, AdaptiveStrategy, AdaptiveConfig

# BaseBot 임포트를 위한 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bots.base_bot import BaseBot

# 한국 시간대 설정
KST = timezone(timedelta(hours=9))

PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot.pid')
DYNAMIC_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dynamic_config.json')
PAPER_BALANCE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'paper_balance.json')
PAPER_POSITION_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'paper_position.json')
TRADING_STATUS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading_status.json')

def create_pid_file():
    """PID 파일 생성"""
    pid = os.getpid()
    with open(PID_FILE, 'w') as f:
        f.write(str(pid))
    logger.info(f"Created PID file: {PID_FILE} (PID: {pid})")

def remove_pid_file():
    """PID 파일 삭제"""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
        logger.info(f"Removed PID file: {PID_FILE}")

class KSTFormatter(logging.Formatter):
    """한국 시간대 포맷터"""
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt, style='{') # Pass datefmt to super, and specify style
        self._datefmt = datefmt # Store datefmt explicitly for formatTime
        self.converter = lambda x: datetime.fromtimestamp(x, KST)

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        if datefmt:
            return ct.strftime(datefmt)
        # If datefmt is not provided to formatTime, use the one stored in the formatter
        return ct.strftime(self._datefmt if self._datefmt else '%Y-%m-%d %H:%M:%S')

    def format(self, record):
        # The super().format() method will call formatTime with self.datefmt (which is now correctly set by super().__init__)
        # However, to ensure our custom formatTime uses the correct datefmt, we pass it explicitly.
        record.asctime = self.formatTime(record, self._datefmt)
        return super().format(record)

class FlushFileHandler(logging.FileHandler):
    """즉시 flush하는 파일 핸들러"""
    def emit(self, record):
        super().emit(record)
        self.flush()

# 로깅 설정
logger = logging.getLogger('live_trader')
logger.setLevel(logging.INFO)

if logger.handlers:
    logger.handlers.clear()

# 1. 콘솔 핸들러
console_handler = logging.StreamHandler()
console_handler.setFormatter(KSTFormatter(fmt='[{asctime}] {levelname}: {message}', datefmt='%H:%M:%S'))
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

# 2. 파일 핸들러 (대시보드 실시간 반영을 위해 bot.log에 직접 기록)
file_handler = FlushFileHandler(cfg.LOG_FILE, encoding='utf-8')
file_handler.setFormatter(KSTFormatter(fmt='{asctime} | {levelname} | {message}', datefmt='%Y-%m-%d %H:%M:%S'))
file_handler.setLevel(logging.INFO)
logger.addHandler(file_handler)

def print_startup():
    """시작 메시지 출력"""
    print("=" * 60)
    print("🏆 바이비트 실거래 봇 시작 (Integrated Adaptive + ML Filter)")
    print("=" * 60)
    print(f"📊 심볼: {cfg.SYMBOL}")
    print(f"⏱️ 타임프레임: {cfg.TIMEFRAME}m")
    print(f"🚀 기본 레버리지: {cfg.LEVERAGE}x")
    print(f"🕒 거래 시간: {cfg.SESSION_START_HOUR}:00 - {cfg.SESSION_END_HOUR}:00 (KST)")
    print(f"🌐 테스트넷: {cfg.USE_TESTNET}")
    if getattr(cfg, 'PAPER_TRADING', False):
        print(f"📝 페이퍼 트레이딩: ON (가상 거래)")
    
    if os.path.exists(DYNAMIC_CONFIG_PATH):
        print(f"✨ 동적 파라미터 적용 중: {DYNAMIC_CONFIG_PATH}")
    
    print("-" * 60)
    print(f"📝 로그 파일: {cfg.LOG_FILE}")
    print("=" * 60)
    print()

class LiveTrader(BaseBot):
    def execute_logic(self):
        pass

    def __init__(self):
        super().__init__(name="Bot_1H", interval="1h")
        # Manager Attributes
        self.current_balance = 0.0
        self.status = "Initializing"
        self.balance_history = []
        self.current_position = None
        self.liquidation_price = 0
        self.liquidation_profit = 0
        self.total_roi = 0
        self.max_history = 50
        
        print_startup()
        
        # Paper Mode key handling
        api_key = cfg.BYBIT_API_KEY
        api_secret = cfg.BYBIT_API_SECRET
        if getattr(cfg, 'PAPER_TRADING', False):
             api_key = "" # Empty key for public access only
             api_secret = ""
             
        self.client = BybitClient(api_key, api_secret, testnet=cfg.USE_TESTNET)
        
        # Initialize strategy with default config
        self.config = AdaptiveConfig(
            leverage=cfg.LEVERAGE,
            adx_trending_min=cfg.ADX_TRENDING_MIN,
            adx_ranging_max=cfg.ADX_RANGING_MAX,
            trend_sl_atr=cfg.TREND_SL_ATR,
            range_sl_atr=cfg.RANGE_SL_ATR,
            session_start_hour=cfg.SESSION_START_HOUR,
            session_end_hour=cfg.SESSION_END_HOUR
        )
        self.load_dynamic_config()
        self.strategy = AdaptiveStrategy(config=self.config)
        
        self.current_position = None
        self.last_exit_price = self.load_last_exit_price()
        self.last_optimize_date = self.load_last_optimize_date()
        self.instrument_info = None
        self.sync_position()

    def load_last_exit_price(self):
        """마지막 종료가 로드"""
        try:
            if os.path.exists(TRADING_STATUS_PATH):
                with open(TRADING_STATUS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('last_exit_price')
        except Exception as e:
            logger.error(f"Error loading last exit price: {e}")
        return None

    def load_last_optimize_date(self):
        """마지막 최적화 날짜 로드"""
        try:
            if os.path.exists(DYNAMIC_CONFIG_PATH):
                with open(DYNAMIC_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    date_str = data.get('last_optimized_date')
                    if date_str:
                        return datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception as e:
            logger.error(f"Error loading last optimize date: {e}")
        return None

    def load_paper_balance(self):
        """가상 잔고 로드"""
        if os.path.exists(PAPER_BALANCE_PATH):
            try:
                with open(PAPER_BALANCE_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return float(data.get('balance', 100.0))
            except:
                pass
        return 100.0

    def save_paper_balance(self, balance):
        """가상 잔고 저장"""
        try:
            with open(PAPER_BALANCE_PATH, 'w', encoding='utf-8') as f:
                json.dump({'balance': balance, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving paper balance: {e}")

    def load_paper_position(self):
        """가상 포지션 로드"""
        if os.path.exists(PAPER_POSITION_PATH):
            try:
                with open(PAPER_POSITION_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return None

    def save_paper_position(self, position):
        """가상 포지션 저장"""
        try:
            with open(PAPER_POSITION_PATH, 'w', encoding='utf-8') as f:
                if position:
                    json.dump(position, f, indent=4)
                else:
                    f.write("{}")
        except Exception as e:
            logger.error(f"Error saving paper position: {e}")

    def save_last_optimize_date(self, date):
        """마지막 최적화 날짜 저장"""
        try:
            data = {}
            if os.path.exists(DYNAMIC_CONFIG_PATH):
                with open(DYNAMIC_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            
            data['last_optimized_date'] = date.strftime('%Y-%m-%d')
            with open(DYNAMIC_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving last optimize date: {e}")

    def load_dynamic_config(self):
        """dynamic_config.json에서 최신 파라미터 로드"""
        if os.path.exists(DYNAMIC_CONFIG_PATH):
            try:
                with open(DYNAMIC_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    p = data.get('parameters', {})
                    if p:
                        self.config.leverage = p.get('leverage', self.config.leverage)
                        self.config.adx_trending_min = p.get('adx_trending_min', self.config.adx_trending_min)
                        self.config.adx_ranging_max = p.get('adx_ranging_max', self.config.adx_ranging_max)
                        self.config.trend_sl_atr = p.get('trend_sl_atr', self.config.trend_sl_atr)
                        self.config.range_sl_atr = p.get('range_sl_atr', self.config.range_sl_atr)
                        self.config.session_start_hour = p.get('session_start_hour', self.config.session_start_hour)
                        self.config.session_end_hour = p.get('session_end_hour', self.config.session_end_hour)
                        logger.info(f"Dynamic config loaded into strategy: {p}")
            except Exception as e:
                logger.error(f"Error loading dynamic config: {e}")

    def save_trading_status(self, current_price, status_msg="정상 실행 중"):
        """현재 트레이딩 상태를 파일로 저장 (대시보드 연동용)"""
        try:
            balance = 0
            if getattr(cfg, 'PAPER_TRADING', False):
                balance = self.load_paper_balance()
            else:
                try:
                    balance_info = self.client.get_balance()
                    for coin in balance_info.get('list', [])[0].get('coin', []):
                        if coin['coin'] == 'USDT':
                            balance = float(coin['walletBalance'])
                            break
                except Exception as e:
                    logger.error(f"Error fetching real balance for status: {e}")

            status_data = {
                'timestamp': datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S'),
                'symbol': cfg.SYMBOL,
                'current_price': current_price,
                'balance': balance,
                'position': self.current_position,
                'last_exit_price': self.last_exit_price,
                'status_message': status_msg,
                'paper_trading': getattr(cfg, 'PAPER_TRADING', False)
            }
            
            with open(TRADING_STATUS_PATH, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving trading status: {e}")

    def get_qty_step(self):
        """심볼의 최소 주문 단위(qtyStep) 조회"""
        if not self.instrument_info:
            self.instrument_info = self.client.get_instrument_info(cfg.SYMBOL)
        
        try:
            qty_step = self.instrument_info.get('lotSizeFilter', {}).get('qtyStep', '0.001')
            return float(qty_step)
        except:
            return 0.001

    def get_price_tick(self):
        """심볼의 최소 가격 단위(tickSize) 조회"""
        if not self.instrument_info:
            self.instrument_info = self.client.get_instrument_info(cfg.SYMBOL)
            
        try:
            tick_size = self.instrument_info.get('priceFilter', {}).get('tickSize', '0.01')
            return float(tick_size)
        except:
            return 0.01

    def round_qty(self, qty):
        """qtyStep에 맞춰 수량 반올림"""
        step = self.get_qty_step()
        precision = 0
        if step < 1:
            precision = len(str(step).split('.')[-1])
        return round(qty, precision)

    def round_price(self, price):
        """tickSize에 맞춰 가격 반올림"""
        tick = self.get_price_tick()
        precision = 0
        if tick < 1:
            precision = len(str(tick).split('.')[-1])
        return round(price, precision)

    def check_and_optimize(self):
        now_kst = datetime.now(KST)
        today = now_kst.date()
        
        if self.last_optimize_date != today:
            logger.info("Starting daily auto-optimization...")
            try:
                optimizer_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'auto_optimizer.py')
                # Capture output to log file directly instead of buffering in memory
                result = subprocess.run(['python3', '-u', optimizer_path], check=False)
                
                if result.returncode == 0:
                    logger.info("Auto-optimization completed successfully.")
                    self.load_dynamic_config()
                    self.last_optimize_date = today
                    self.save_last_optimize_date(today)
                else:
                    logger.error(f"Auto-optimization failed: {result.stderr}")
            except Exception as e:
                logger.error(f"Error during auto-optimization: {e}")

    def sync_position(self):
        if getattr(cfg, 'PAPER_TRADING', False):
            self.current_position = self.load_paper_position()
            if self.current_position:
                logger.info(f"Paper position synced: {self.current_position}")
            return

        try:
            pos = self.client.get_positions(cfg.SYMBOL)
            if pos and float(pos[0]['size']) > 0:
                side = 'buy' if pos[0]['side'] == 'Buy' else 'sell'
                sl = float(pos[0].get('stopLoss', 0))
                self.current_position = {
                    'side': side,
                    'entry_price': float(pos[0]['avgPrice']),
                    'qty': float(pos[0]['size']),
                    'regime': 'unknown',
                    'sl': sl
                }
                logger.info(f"Existing position synced: {side} at {self.current_position['entry_price']}, Qty: {self.current_position['qty']}, SL: {sl}")
            else:
                self.current_position = None
        except Exception as e:
            logger.error(f"Sync position error: {e}")

    def stop(self):
        self.is_running = False
        self.status = "Stopped"
        logger.info("Stopping 1H Bot...")
    
    def wait_while_running(self, seconds):
        if not hasattr(self, 'is_running'):
             time.sleep(seconds)
             return
        for _ in range(seconds):
            if not self.is_running:
                break
            time.sleep(1)

    def run(self):
        logger.info("Bot starting main loop...")
        self.is_running = True
        
        while self.is_running:
            try:
                from datetime import datetime
                self.last_run = datetime.now()
                
                self.check_and_optimize()
                
                # 1. Fetch Data
                # Get 200 candles to ensure indicators are stable
                klines = self.client.get_klines(cfg.SYMBOL, interval=cfg.TIMEFRAME, limit=200)
                if not klines:
                    logger.warning("Failed to fetch klines, retrying...")
                    time.sleep(10)
                    continue
                
                # Convert klines to DataFrame
                # Bybit V5: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df['close'] = df['close'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['open'] = df['open'].astype(float)
                df['volume'] = df['volume'].astype(float)
                
                # Bybit returns newest first, so we reverse it
                df = df.iloc[::-1].reset_index(drop=True)
                
                # 차트용 데이터 저장 (최근 100개만)
                self.recent_candles = [
                    {'x': int(row['timestamp']), 'y': [row['open'], row['high'], row['low'], row['close']]}
                    for index, row in df.tail(100).iterrows()
                ]
                
                # Add indicators
                df = add_indicators(df)
                curr_row = df.iloc[-1]
                curr_price = curr_row['close']
                
                # 2. Status Logging (One-line summary)
                balance = 0
                if getattr(cfg, 'PAPER_TRADING', False):
                    balance = self.load_paper_balance()
                else:
                    try:
                        balance_info = self.client.get_balance()
                        for coin in balance_info.get('list', [])[0].get('coin', []):
                            if coin['coin'] == 'USDT':
                                balance = float(coin['walletBalance'])
                                break
                    except: pass

                pos_str = "None"
                if self.current_position:
                    pos_str = f"{self.current_position['side'].upper()} ({self.current_position['qty']})"
                
                mode_str = "PAPER" if getattr(cfg, 'PAPER_TRADING', False) else "REAL"
                
                if pos_str == "None":
                    status_msg = "신호 대기 중"
                else:
                    status_msg = f"포지션 보유 중 ({pos_str})"
                
                logger.info(f"[{mode_str}] Price: {curr_price:,.1f} | Balance: {balance:,.2f} USDT | Pos: {pos_str} | ATR: {curr_row['atr']:.2f}")
                
                # 대시보드 업데이트
                self.current_balance = balance
                self.status = status_msg
                self.balance_history.append(balance)
                if len(self.balance_history) > self.max_history:
                    self.balance_history.pop(0)
                
                # Update status
                self.save_trading_status(curr_price, status_msg)
                
                # 2. Position Management
                if self.current_position:
                    should_exit, reason = self.strategy.check_exit(df, self.current_position['side'], self.current_position['regime'])
                    
                    curr_price = curr_row['close']
                    if self.current_position['side'] == 'buy' and self.current_position['sl'] > 0:
                        if curr_price <= self.current_position['sl']:
                            should_exit, reason = True, "ATR Stop Loss"
                    elif self.current_position['side'] == 'sell' and self.current_position['sl'] > 0:
                        if curr_price >= self.current_position['sl']:
                            should_exit, reason = True, "ATR Stop Loss"

                    if should_exit:
                        logger.info(f"Exiting position: {reason}")
                        
                        if getattr(cfg, 'PAPER_TRADING', False):
                            # Calculate PnL for paper trading
                            entry_price = self.current_position['entry_price']
                            qty = self.current_position['qty']
                            exit_price = curr_row['close']
                            
                            if self.current_position['side'] == 'buy':
                                pnl = (exit_price - entry_price) * qty
                            else:
                                pnl = (entry_price - exit_price) * qty
                            
                            current_balance = self.load_paper_balance()
                            new_balance = current_balance + pnl
                            self.save_paper_balance(new_balance)
                            self.save_paper_position(None)
                            self.last_exit_price = exit_price
                            logger.info(f"Paper Trade Exit | PnL: {pnl:.2f} | New Balance: {new_balance:.2f}")
                            self.save_trading_status(curr_price, f"페이퍼 트레이딩 종료 (PnL: {pnl:.2f})")
                        else:
                            side_to_close = 'Sell' if self.current_position['side'] == 'buy' else 'Buy'
                            exit_price = curr_price
                            self.client.close_position(cfg.SYMBOL, side_to_close)
                            self.last_exit_price = exit_price
                            self.save_trading_status(curr_price, f"실거래 포지션 종료")
                            
                        self.current_position = None
                
                # 3. Entry Check
                else:
                    signal = self.strategy.get_signal(df)
                    if signal['side'] != 'none':
                        logger.info(f"Entry Signal: {signal['side']} | Regime: {signal['regime']} | Reason: {signal['reason']}")
                        
                        # Calculate position size
                        usdt_balance = 0
                        if getattr(cfg, 'PAPER_TRADING', False):
                            usdt_balance = self.load_paper_balance()
                        else:
                            balance_info = self.client.get_balance()
                            for coin in balance_info.get('list', [])[0].get('coin', []):
                                if coin['coin'] == 'USDT':
                                    usdt_balance = float(coin['walletBalance'])
                                    break
                        
                        if usdt_balance <= 0:
                            logger.error("Insufficient balance")
                            time.sleep(60)
                            continue

                        # Use 90% of balance with leverage
                        usdt_to_use = usdt_balance * 0.9 * self.config.leverage
                        qty = usdt_to_use / curr_row['close']
                        qty = self.round_qty(qty)
                        
                        # ATR Stop Loss
                        atr = curr_row['atr']
                        sl_dist = atr * (self.config.trend_sl_atr if signal['regime'] == 'trending' else self.config.range_sl_atr)
                        
                        sl_price = curr_row['close'] - sl_dist if signal['side'] == 'buy' else curr_row['close'] + sl_dist
                        
                        # Round SL Price
                        sl_price = self.round_price(sl_price)
                        
                        if getattr(cfg, 'PAPER_TRADING', False):
                            self.current_position = {
                                'side': signal['side'],
                                'entry_price': curr_row['close'],
                                'qty': qty,
                                'regime': signal['regime'],
                                'sl': sl_price
                            }
                            self.save_paper_position(self.current_position)
                            logger.info(f"Paper Trade Entry | Side: {signal['side']} | Price: {curr_row['close']} | Qty: {qty} | SL: {sl_price}")
                            self.save_trading_status(curr_price, f"페이퍼 트레이딩 진입 ({signal['side']})")
                        else:
                            order = self.client.place_order(cfg.SYMBOL, signal['side'], qty, sl_price)
                            if order:
                                self.current_position = {
                                    'side': signal['side'],
                                    'entry_price': curr_row['close'],
                                    'qty': qty,
                                    'regime': signal['regime'],
                                    'sl': sl_price
                                }
                                logger.info(f"Real Trade Entry | Side: {signal['side']} | Price: {curr_row['close']} | Qty: {qty} | SL: {sl_price}")
                                self.save_trading_status(curr_price, f"실거래 진입 ({signal['side']})")
                            else:
                                logger.error("Failed to place order.")
                
                self.wait_while_running(10) # 10초 대기
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                self.wait_while_running(10) # 에러 발생 시에도 10초 대기 후 재시도
                logger.info(f"Entered {signal['side']} at {curr_row['close']}, Qty: {qty}, SL: {sl_price:.2f}")
                self.save_trading_status(curr_price, f"{signal['side']} 포지션 진입")
        
        self.status = "Stopped"
        logger.info("1H Bot Stopped Loop.")

if __name__ == "__main__":
    create_pid_file()
    try:
        trader = LiveTrader()
        trader.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
    finally:
        remove_pid_file()
