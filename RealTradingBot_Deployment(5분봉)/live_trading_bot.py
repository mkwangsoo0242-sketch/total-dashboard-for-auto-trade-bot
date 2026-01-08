import schedule
import subprocess
import threading

# ... (기존 로깅 설정 등)

class LiveTradingBot:
    def __init__(self):
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.secret = os.getenv('BINANCE_SECRET')
        self.mode = os.getenv('TRADING_MODE', 'paper').lower()
        self.symbol = os.getenv('SYMBOL', 'BTC/USDT')
        self.timeframe = '5m'  # 1h -> 5m 수정
        
        # 모델 로드
        self.model_ts = 0
        self.load_models()
        self.start_scheduler()
        
        # 거래소 초기화
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        # ... (기존 모드 체크)
        
        logging.info(f"봇 초기화 완료: {self.symbol} ({self.timeframe})")

    def start_scheduler(self):
        def job():
            logging.info("⏰ 00:00 정기 재학습 시작...")
            subprocess.Popen([sys.executable, "retrain.py"])
            
        schedule.every().day.at("00:00").do(job)
        
        def run_schedule():
            while True:
                schedule.run_pending()
                time.sleep(60)
                
        try:
            t = threading.Thread(target=run_schedule, daemon=True)
            t.start()
            logging.info("📅 자동 재학습 스케줄러 가동 (매일 00:00)")
        except Exception as e:
            logging.error(f"스케줄러 시작 실패: {e}")

    def check_model_reload(self):
        try:
            # 5분봉 봇은 short_model.pkl (이름 주의)
            path = 'short_model.pkl' 
            if os.path.exists(path):
                mtime = os.path.getmtime(path)
                if mtime > self.model_ts:
                    logging.info("🔄 새로운 모델 파일 감지! 다시 로드합니다.")
                    self.load_models()
        except: pass

    def load_models(self):
        """다중 모델 로드"""
        try:
            logging.info("🤖 ML 모델 로딩...")
            
            path = 'short_model.pkl'
            if os.path.exists(path):
                self.model_ts = os.path.getmtime(path)
                
            self.short_model_data = joblib.load('short_model.pkl')
            self.long_model_data = joblib.load('long_model.pkl')
            self.regime_model_data = joblib.load('regime_model.pkl')
            
            self.short_model = self.short_model_data['model']
            self.long_model = self.long_model_data['model']
            self.regime_model = self.regime_model_data['model']
            
            logging.info(f"   Short 모델 정확도: {self.short_model_data.get('accuracy', 0)*100:.1f}%") # get 처리
            logging.info(f"   Long 모델 정확도: {self.long_model_data.get('accuracy', 0)*100:.1f}%")
            logging.info(f"   Regime 모델 정확도: {self.regime_model_data.get('accuracy', 0)*100:.1f}%")
        except Exception as e:
            logging.error(f"모델 로드 실패: {e}")
            if not hasattr(self, 'short_model'):
                sys.exit(1)

    def fetch_data(self, limit=250):
        """데이터 수집 및 전처리"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # 지표 추가 (strategy.py 사용)
            df = add_indicators(df)
            
            # 추가 피처 (훈련 시와 동일하게)
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
            logging.error(f"데이터 수집 중 오류: {e}")
            return None

    def get_features(self, row, feature_list):
        """모델 입력 피처 추출"""
        features = {}
        for f in feature_list:
            val = row.get(f, 0)
            features[f] = val if not pd.isna(val) else 0
        return pd.DataFrame([features])

    def predict_regime(self, row):
        """시장 레짐 예측"""
        try:
            features = self.get_features(row, self.regime_model_data['features'])
            return int(self.regime_model.predict(features)[0])
        except:
            return 0 # 기본값 SIDEWAYS

    def predict_probs(self, row):
        """Long/Short 확률 예측"""
        try:
            l_feat = self.get_features(row, self.long_model_data['features'])
            s_feat = self.get_features(row, self.short_model_data['features'])
            
            l_prob = self.long_model.predict_proba(l_feat)[0][1]
            s_prob = self.short_model.predict_proba(s_feat)[0][1]
            
            return l_prob, s_prob
        except:
            return 0.5, 0.5

    def get_position(self):
        """현재 포지션 조회"""
        try:
            balance = self.exchange.fetch_balance()
            positions = balance['info']['positions']
            for pos in positions:
                if pos['symbol'] == self.symbol.replace('/', ''):
                    amt = float(pos['positionAmt'])
                    if amt != 0:
                        return {'amount': amt, 'entry': float(pos['entryPrice']), 'type': 'long' if amt > 0 else 'short'}
            return None
        except Exception as e:
            logging.error(f"포지션 조회 실패: {e}")
            return None

    def execute_trade(self, signal, amount, leverage):
        """주문 실행"""
        if self.mode == 'paper':
            logging.info(f"🧪 [PAPER] {signal} 주문 시뮬레이션: 수량 {amount}, 레버리지 {leverage}")
            return True
        
        try:
            # 레버리지 설정
            self.exchange.set_leverage(leverage, self.symbol)
            
            side = 'buy' if signal == 'long' else 'sell'
            order = self.exchange.create_market_order(self.symbol, side, amount)
            logging.info(f"✅ 주문 체결: {side} {amount} {self.symbol}")
            return order
        except Exception as e:
            logging.error(f"주문 실패: {e}")
            return None

    def close_position(self):
        """포지션 종료"""
        pos = self.get_position()
        if pos:
            amount = abs(pos['amount'])
            side = 'sell' if pos['type'] == 'long' else 'buy'
            if self.mode == 'paper':
                logging.info(f"🧪 [PAPER] 포지션 종료 시뮬레이션: {side} {amount}")
            else:
                try:
                    self.exchange.create_market_order(self.symbol, side, amount)
                    logging.info("✅ 포지션 종료 완료")
                except Exception as e:
                    logging.error(f"포지션 종료 실패: {e}")

    def run(self):
        logging.info("🚀 라이브 트레이딩 봇 시작 (다중 ML 모델)")
        
        while True:
            try:
                # 1. 데이터 수집
                df = self.fetch_data()
                if df is None:
                    time.sleep(60)
                    continue
                
                current = df.iloc[-1]
                price = current['close']
                
                # 2. 포지션 확인
                position = self.get_position()
                
                # 3. 신호 생성
                regime = self.predict_regime(current)
                settings = REGIME_SETTINGS.get(regime, {'skip': True})
                
                settings_name = settings.get('name', 'UNKNOWN')
                logging.info(f"📊 현재 시장 레짐: {settings_name} (가격: {price:,.2f})")
                
                if position:
                    logging.info(f"🔥 포지션 보유 중: {position['type']} {position['amount']}")
                    # 여기서 청산 로직 추가 가능 (SL/TP 등)
                    # 현재는 전략에 맡김
                
                elif not settings.get('skip'):
                    l_prob, s_prob = self.predict_probs(current)
                    direction = settings['direction']
                    threshold = settings['threshold']
                    
                    signal = None
                    if direction == 'long' and l_prob > threshold:
                        signal = 'long'
                        logging.info(f"🔍 Long 신호 감지! (확률: {l_prob:.2%})")
                    elif direction == 'short' and s_prob > threshold:
                        signal = 'short'
                        logging.info(f"🔍 Short 신호 감지! (확률: {s_prob:.2%})")
                    
                    if signal:
                        # 자금 관리
                        balance = self.exchange.fetch_balance()['USDT']['free']
                        risk = settings['risk']
                        leverage = settings['leverage']
                        
                        # ATR 기반 포지션 사이징
                        atr = current['atr'] if not pd.isna(current['atr']) else price * 0.01
                        sl_pct = (atr * settings['sl_mult']) / price
                        
                        risk_amt = balance * risk
                        target_size = risk_amt / sl_pct
                        max_size = balance * leverage
                        
                        final_size_usd = min(target_size, max_size)
                        amount = final_size_usd / price
                        
                        logging.info(f"🚀 진입 결정: {signal} | 크기: ${final_size_usd:.2f} ({amount:.4f} BTC)")
                        self.execute_trade(signal, amount, leverage)
                else:
                    logging.info("⏸️ 횡보장 또는 스킵 구간 - 관망")
                
                logging.info("💤 다음 캔들 대기 (5분)...")
                
                # 모델 업데이트 체크
                self.check_model_reload()
                
                time.sleep(300)  # 5분 대기
                
            except KeyboardInterrupt:
                logging.info("⏹️ 봇 중지")
                break
            except Exception as e:
                logging.error(f"예기치 않은 오류: {e}")
                time.sleep(60)

if __name__ == "__main__":
    bot = LiveTradingBot()
    bot.run()
