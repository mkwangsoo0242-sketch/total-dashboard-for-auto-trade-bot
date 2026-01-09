#!/usr/bin/env python3
"""
바이비트 실거래 봇 - 웹 대시보드 (통합 버전)
Flask를 사용한 웹 기반 모니터링 및 관리
"""

import os
import sys
import json
import subprocess
import psutil
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request
import pandas as pd

# 현재 디렉토리를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

import config as cfg

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# 전역 변수
BOT_PROCESS = None
PID_FILE = os.path.join(current_dir, 'bot.pid')
TRADER_SCRIPT = 'live_trader_bybit.py'

class BotManager:
    """봇 관리 클래스"""
    
    def __init__(self):
        self.log_file = cfg.LOG_FILE
        self.results_dir = cfg.RESULTS_DIR
        self.trades_file = os.path.join(self.results_dir, cfg.TRADES_LOG_FILE)
        self.compound_file = os.path.join(self.results_dir, 'compound_events.csv')
        self.status_file = os.path.join(current_dir, 'trading_status.json')
    
    def get_trading_status(self):
        """트레이딩 상세 상태 조회 (잔고, 포지션, 현재가 등)"""
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"상태 파일 읽기 오류: {e}")
        return None

    def get_bot_status(self):
        """봇 상태 조회"""
        # PID 파일로 상태 확인
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, 'r') as f:
                    pid = int(f.read().strip())
                
                # 프로세스 존재 확인
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    if proc.is_running():
                        # 프로세스가 우리가 실행한 스크립트인지 확인
                        cmdline = proc.cmdline()
                        if any(TRADER_SCRIPT in cmd for cmd in cmdline):
                            return {
                                'status': 'running',
                                'message': '봇 실행 중',
                                'is_running': True,
                                'pid': pid,
                                'uptime': str(datetime.now() - datetime.fromtimestamp(proc.create_time())).split('.')[0]
                            }
            except Exception as e:
                print(f"PID 확인 오류: {e}")
        
        # PID 파일이 없거나 유효하지 않으면 프로세스 직접 확인
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline'] or []
                if any(TRADER_SCRIPT in cmd for cmd in cmdline):
                    return {
                        'status': 'running',
                        'message': '봇 실행 중 (PID 파일 없음)',
                        'is_running': True,
                        'pid': proc.info['pid']
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # 로그 파일로 최근 활동 확인
        if os.path.exists(self.log_file):
            try:
                mtime = os.path.getmtime(self.log_file)
                last_modified = datetime.fromtimestamp(mtime)
                time_diff = (datetime.now() - last_modified).total_seconds()
                
                if time_diff < 60:  # 1분 이내 로그 업데이트
                    return {
                        'status': 'unknown',
                        'message': '봇 상태 불명확 (최근 로그 있음)',
                        'is_running': False,
                        'last_log_time': last_modified.strftime('%Y-%m-%d %H:%M:%S')
                    }
            except Exception:
                pass
        
        return {
            'status': 'stopped',
            'message': '봇 중지됨',
            'is_running': False
        }
    
    def get_latest_logs(self, lines=100):
        """최신 로그 조회 (효율적인 방식)"""
        if not os.path.exists(self.log_file):
            return []
        
        try:
            # 파일의 마지막 부분을 읽기 위해 collections.deque 사용
            from collections import deque
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                # 마지막 lines만큼의 줄만 유지
                last_lines = deque(f, maxlen=lines)
            
            result = []
            last_line = None
            for line in last_lines:
                line = line.strip()
                if not line:
                    continue
                # 중복 라인 필터링 (연속된 동일 로그 방지)
                if line != last_line:
                    result.append(line)
                    last_line = line
            return result
        except Exception as e:
            return [f"로그 읽기 오류: {e}"]
    
    def get_trade_stats(self):
        """거래 통계 조회"""
        if not os.path.exists(self.trades_file):
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'recent_trades': []
            }
        
        try:
            df = pd.read_csv(self.trades_file)
            
            if len(df) == 0:
                return {
                    'total_trades': 0,
                    'wins': 0,
                    'losses': 0,
                    'win_rate': 0,
                    'total_pnl': 0,
                    'avg_pnl': 0,
                    'recent_trades': []
                }
            
            wins = len(df[df['pnl_net'] > 0])
            losses = len(df[df['pnl_net'] <= 0])
            win_rate = (wins / len(df) * 100) if len(df) > 0 else 0
            total_pnl = float(df['pnl_net'].sum())
            avg_pnl = float(df['pnl_net'].mean())
            
            # 최근 거래 (안전하게 처리)
            recent_trades = []
            try:
                for idx, row in df.tail(10).iloc[::-1].iterrows():
                    recent_trades.append({
                        'entry_time': str(row.get('entry_time', '')),
                        'exit_time': str(row.get('exit_time', '')),
                        'side': str(row.get('side', 'unknown')),
                        'entry_price': float(row.get('entry_price', 0)),
                        'exit_price': float(row.get('exit_price', 0)),
                        'pnl': float(row.get('pnl', 0)),
                        'pnl_net': float(row.get('pnl_net', 0)),
                        'reason': str(row.get('reason', '일반'))
                    })
            except Exception as e:
                print(f"최근 거래 처리 오류: {e}")
                recent_trades = []
            
            return {
                'total_trades': len(df),
                'wins': wins,
                'losses': losses,
                'win_rate': round(win_rate, 2),
                'total_pnl': round(total_pnl, 2),
                'avg_pnl': round(avg_pnl, 4),
                'recent_trades': recent_trades
            }
        except Exception as e:
            print(f"거래 통계 조회 오류: {e}")
            return {
                'error': str(e),
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'recent_trades': []
            }
    
    def get_compound_stats(self):
        """복리 통계 조회"""
        if not os.path.exists(self.compound_file):
            return {
                'total_compounds': 0,
                'final_balance': 0,
                'total_profit': 0,
                'recent_compounds': []
            }
        
        try:
            df = pd.read_csv(self.compound_file)
            
            if len(df) == 0:
                return {
                    'total_compounds': 0,
                    'final_balance': 0,
                    'total_profit': 0,
                    'recent_compounds': []
                }
            
            final_balance = float(df['balance_after'].iloc[-1])
            total_profit = float(df['profit_added'].sum())
            
            # 최근 복리
            recent_compounds = []
            for idx, row in df.tail(5).iloc[::-1].iterrows():
                recent_compounds.append({
                    'timestamp': str(row['timestamp']),
                    'balance_before': float(row['balance_before']),
                    'balance_after': float(row['balance_after']),
                    'profit_added': float(row['profit_added'])
                })
            
            return {
                'total_compounds': len(df),
                'final_balance': round(final_balance, 2),
                'total_profit': round(total_profit, 2),
                'recent_compounds': recent_compounds
            }
        except Exception as e:
            return {
                'error': str(e),
                'total_compounds': 0
            }
    
    def start_bot(self):
        """봇 시작"""
        try:
            # 이미 실행 중인지 확인
            status = self.get_bot_status()
            if status['is_running']:
                return {'success': False, 'message': '봇이 이미 실행 중입니다'}
            
            # 로그 파일 경로
            log_file = self.log_file
            
            # 봇 프로세스 시작 (nohup으로 백그라운드 실행)
            if os.name == 'nt':  # Windows
                subprocess.Popen(['python', TRADER_SCRIPT], 
                               cwd=current_dir,
                               creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:  # Linux/Mac
                # nohup으로 백그라운드 실행
                # PID 파일은 live_trader_bybit.py 내부에서 생성함
                cmd = f'cd "{current_dir}" && nohup python3 {TRADER_SCRIPT} >> "{log_file}" 2>&1 &'
                subprocess.Popen(cmd, shell=True)
            
            import time
            time.sleep(2)
            
            # 시작 확인
            new_status = self.get_bot_status()
            if new_status['is_running']:
                return {'success': True, 'message': f'봇이 시작되었습니다 (PID: {new_status.get("pid", "unknown")})'}
            else:
                return {'success': True, 'message': '봇 시작 요청됨 (확인 중...)'}
                
        except Exception as e:
            return {'success': False, 'message': f'봇 시작 오류: {e}'}
    
    def stop_bot(self):
        """봇 중지"""
        try:
            status = self.get_bot_status()
            if not status['is_running']:
                return {'success': False, 'message': '실행 중인 봇을 찾을 수 없습니다'}
            
            pid = status.get('pid')
            killed = False
            
            if pid:
                try:
                    proc = psutil.Process(pid)
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        proc.kill()
                    killed = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # 혹시 PID 파일이 남아있다면 삭제 (실제로는 봇 내부의 finally에서 삭제하지만)
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            
            if killed:
                return {'success': True, 'message': '봇이 중지되었습니다'}
            else:
                return {'success': False, 'message': '봇 중지에 실패했거나 이미 중지되었습니다'}
        except Exception as e:
            return {'success': False, 'message': f'봇 중지 오류: {e}'}
    
    def restart_bot(self):
        """봇 재시작"""
        try:
            # 먼저 중지
            self.stop_bot()
            
            # 잠시 대기
            import time
            time.sleep(2)
            
            # 다시 시작
            start_result = self.start_bot()
            
            if start_result['success']:
                return {'success': True, 'message': '봇이 재시작되었습니다'}
            else:
                return {'success': False, 'message': f'봇 재시작 실패: {start_result["message"]}'}
        except Exception as e:
            return {'success': False, 'message': f'봇 재시작 오류: {e}'}

# 봇 관리자 인스턴스
bot_manager = BotManager()

# ============================================================================
# API 엔드포인트
# ============================================================================

@app.route('/')
def index():
    """메인 페이지"""
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """봇 상태 API"""
    status = bot_manager.get_bot_status()
    trading_status = bot_manager.get_trading_status()
    if trading_status:
        status['trading'] = trading_status
    status['timestamp'] = datetime.now().isoformat()
    return jsonify(status)

@app.route('/api/logs')
def api_logs():
    """로그 API"""
    lines = request.args.get('lines', 100, type=int)
    logs = bot_manager.get_latest_logs(lines)
    return jsonify({'logs': logs})

@app.route('/api/trades')
def api_trades():
    """거래 통계 API"""
    stats = bot_manager.get_trade_stats()
    return jsonify(stats)

@app.route('/api/compounds')
def api_compounds():
    """복리 통계 API"""
    stats = bot_manager.get_compound_stats()
    return jsonify(stats)

@app.route('/api/dashboard')
def api_dashboard():
    """전체 대시보드 데이터 API"""
    try:
        real_status = bot_manager.get_bot_status()
        trading_status = bot_manager.get_trading_status()
        if trading_status:
            real_status['trading'] = trading_status
            
        real_trades = bot_manager.get_trade_stats()
        real_compounds = bot_manager.get_compound_stats()
        real_logs = bot_manager.get_latest_logs(50)
        
        return jsonify({
            'status': real_status,
            'logs': real_logs if real_logs else [],
            'trades': real_trades,
            'compounds': real_compounds,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"대시보드 API 오류: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/bot/start', methods=['POST'])
def api_bot_start():
    """봇 시작 API"""
    result = bot_manager.start_bot()
    return jsonify(result)

@app.route('/api/bot/stop', methods=['POST'])
def api_bot_stop():
    """봇 중지 API"""
    result = bot_manager.stop_bot()
    return jsonify(result)

@app.route('/api/bot/restart', methods=['POST'])
def api_bot_restart():
    """봇 재시작 API"""
    result = bot_manager.restart_bot()
    return jsonify(result)

@app.route('/api/performance-history')
def api_performance_history():
    """성과 히스토리 API (차트용)"""
    try:
        if not os.path.exists(bot_manager.trades_file):
            return jsonify([])
        
        df = pd.read_csv(bot_manager.trades_file)
        if len(df) == 0:
            return jsonify([])
        
        # 누적 수익률 계산
        df['cumulative_pnl'] = df['pnl_net'].cumsum()
        df['timestamp'] = pd.to_datetime(df['exit_time'])
        
        # 차트용 데이터 포맷
        performance_data = []
        for idx, row in df.iterrows():
            performance_data.append({
                'timestamp': row['timestamp'].isoformat(),
                'cumulative_pnl': float(row['cumulative_pnl']),
                'trade_pnl': float(row['pnl_net'])
            })
        
        return jsonify(performance_data)
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/history')
def api_history():
    """차트 히스토리 데이터 API - Bybit API 연동"""
    try:
        import requests
        import time
        
        timeframe = request.args.get('timeframe', '15m')
        limit = request.args.get('limit', 200, type=int)
        symbol = getattr(cfg, 'SYMBOL', 'BTCUSDT')
        
        timeframe_map = {'1m': '1', '5m': '5', '15m': '15', '30m': '30', '1h': '60', '4h': '240', '1d': 'D'}
        interval = timeframe_map.get(timeframe, '15')
        
        try:
            use_testnet = getattr(cfg, 'USE_TESTNET', True)
            base_url = 'https://api-testnet.bybit.com' if use_testnet else 'https://api.bybit.com'
            
            url = f'{base_url}/v5/market/kline'
            params = {
                'category': 'linear',
                'symbol': symbol,
                'interval': interval,
                'limit': min(limit, 200)
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('retCode') == 0 and result.get('result', {}).get('list'):
                    klines = result['result']['list']
                    data = []
                    for kline in reversed(klines):
                        data.append({
                            'time': int(kline[0]) // 1000,
                            'open': float(kline[1]),
                            'high': float(kline[2]),
                            'low': float(kline[3]),
                            'close': float(kline[4])
                        })
                    return jsonify(data)
        except Exception as api_error:
            print(f"Bybit API 호출 실패: {api_error}")
        
        return jsonify([])
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/detailed-stats')
def api_detailed_stats():
    """상세 통계 API"""
    try:
        if not os.path.exists(bot_manager.trades_file):
            return jsonify({'max_profit': 0, 'max_loss': 0, 'avg_profit': 0, 'sharpe_ratio': 0, 'max_win_streak': 0, 'max_loss_streak': 0})
        
        df = pd.read_csv(bot_manager.trades_file)
        if len(df) == 0:
            return jsonify({'max_profit': 0, 'max_loss': 0, 'avg_profit': 0, 'sharpe_ratio': 0, 'max_win_streak': 0, 'max_loss_streak': 0})
        
        profits = df[df['pnl_net'] > 0]['pnl_net']
        losses = df[df['pnl_net'] <= 0]['pnl_net']
        
        max_profit = float(profits.max()) if len(profits) > 0 else 0
        max_loss = float(losses.min()) if len(losses) > 0 else 0
        avg_profit = float(df['pnl_net'].mean())
        
        returns = df['pnl_net']
        sharpe_ratio = float(returns.mean() / returns.std()) if returns.std() > 0 else 0
        
        win_streak = 0
        loss_streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        
        for pnl in df['pnl_net']:
            if pnl > 0:
                win_streak += 1
                loss_streak = 0
                max_win_streak = max(max_win_streak, win_streak)
            else:
                loss_streak += 1
                win_streak = 0
                max_loss_streak = max(max_loss_streak, loss_streak)
        
        return jsonify({
            'max_profit': round(max_profit, 2),
            'max_loss': round(max_loss, 2),
            'avg_profit': round(avg_profit, 4),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'max_win_streak': max_win_streak,
            'max_loss_streak': max_loss_streak
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/market-data')
def api_market_data():
    """시장 데이터 API"""
    try:
        import requests
        symbol = getattr(cfg, 'SYMBOL', 'BTCUSDT')
        use_testnet = getattr(cfg, 'USE_TESTNET', True)
        base_url = 'https://api-testnet.bybit.com' if use_testnet else 'https://api.bybit.com'
        
        url = f'{base_url}/v5/market/tickers'
        params = {'category': 'linear', 'symbol': symbol}
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('retCode') == 0 and result.get('result', {}).get('list'):
                ticker = result['result']['list'][0]
                return jsonify({
                    'symbol': symbol,
                    'current_price': round(float(ticker.get('lastPrice', 0)), 2),
                    'price_change_24h': round(float(ticker.get('price24hPcnt', 0)) * 100, 2),
                    'volume_24h': round(float(ticker.get('volume24h', 0)), 2),
                    'high_24h': float(ticker.get('highPrice24h', 0)),
                    'low_24h': float(ticker.get('lowPrice24h', 0)),
                    'source': 'bybit'
                })
        return jsonify({'error': 'Failed to fetch market data'})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """설정 조회/저장 API"""
    if request.method == 'GET':
        return jsonify({
            'SYMBOL': getattr(cfg, 'SYMBOL', 'BTCUSDT'),
            'TIMEFRAME': getattr(cfg, 'TIMEFRAME', '15m'),
            'LEVERAGE': getattr(cfg, 'LEVERAGE', 10),
            'DRY_RUN': getattr(cfg, 'PAPER_TRADING', True),
            'USE_TESTNET': getattr(cfg, 'USE_TESTNET', True)
        })
    
    elif request.method == 'POST':
        # 설정 저장 로직은 dynamic_config.json 또는 config.py 업데이트가 필요함
        return jsonify({'success': False, 'message': '설정 변경은 현재 직접 파일 수정을 권장합니다.'})

@app.route('/api/position')
def api_position():
    """현재 포지션 정보 API"""
    try:
        from bybit_client import BybitClient
        client = BybitClient(cfg.BYBIT_API_KEY, cfg.BYBIT_API_SECRET, testnet=cfg.USE_TESTNET)
        positions = client.get_positions(cfg.SYMBOL)
        
        if positions and float(positions[0]['size']) > 0:
            pos = positions[0]
            return jsonify({
                'has_position': True,
                'symbol': pos.get('symbol'),
                'side': pos.get('side'),
                'size': float(pos.get('size', 0)),
                'entry_price': float(pos.get('avgPrice', 0)),
                'mark_price': float(pos.get('markPrice', 0)),
                'unrealized_pnl': float(pos.get('unrealisedPnl', 0)),
                'leverage': pos.get('leverage'),
                'liq_price': float(pos.get('liqPrice', 0)) if pos.get('liqPrice') else None
            })
        return jsonify({'has_position': False, 'message': '현재 포지션 없음'})
    except Exception as e:
        return jsonify({'error': str(e)})

def main():
    """메인 함수"""
    print("=" * 70)
    print("🏆 바이비트 실거래 봇 - 웹 대시보드 (통합 버전)")
    print("=" * 70)
    print(f"📊 심볼: {cfg.SYMBOL}")
    print(f"⏱️  타임프레임: {cfg.TIMEFRAME}분")
    print(f"🔧 레버리지: {cfg.LEVERAGE}x")
    print(f"🌐 테스트넷: {cfg.USE_TESTNET}")
    print("=" * 70)
    print("\n🚀 웹 대시보드 시작...")
    print("📱 브라우저에서 열기: http://localhost:5000")
    print("🛑 중지: Ctrl + C")
    print("=" * 70 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()
