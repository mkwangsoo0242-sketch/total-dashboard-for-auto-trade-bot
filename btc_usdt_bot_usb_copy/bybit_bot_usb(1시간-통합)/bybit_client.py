"""
바이비트 API 클라이언트
"""

import requests
import json
import urllib.parse
import time
import hmac
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class BybitClient:
    """바이비트 API 클라이언트"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """
        초기화
        
        Args:
            api_key: 바이비트 API 키
            api_secret: 바이비트 API 시크릿
            testnet: 테스트넷 사용 여부
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        if testnet:
            self.base_url = "https://api-testnet.bybit.com"
        else:
            self.base_url = "https://api.bybit.com"
        
        self.session = requests.Session()
        headers = {
            'Content-Type': 'application/json'
        }
        if self.api_key:
            headers['X-BAPI-API-KEY'] = self.api_key
            
        self.session.headers.update(headers)
    
    def _generate_signature(self, payload: str, timestamp: str, recv_window: str) -> str:
        """Bybit V5 서명 생성"""
        message = f"{timestamp}{self.api_key}{recv_window}{payload}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, public: bool = False) -> Dict:
        """API 요청"""
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            request_headers = self.session.headers.copy()
            
            if method == 'GET':
                payload = ""
                if params:
                    # Bybit V5 GET: query string is the payload
                    payload = urllib.parse.urlencode(params)
                
                if not public:
                    signature = self._generate_signature(payload, timestamp, recv_window)
                    headers = {
                        'X-BAPI-TIMESTAMP': timestamp,
                        'X-BAPI-SIGN': signature,
                        'X-BAPI-RECV-WINDOW': recv_window
                    }
                    request_headers.update(headers)
                
                response = self.session.get(url, params=params, headers=request_headers, timeout=10)
                
            elif method == 'POST':
                payload = json.dumps(params) if params else ""
                
                if not public:
                    signature = self._generate_signature(payload, timestamp, recv_window)
                    headers = {
                        'X-BAPI-TIMESTAMP': timestamp,
                        'X-BAPI-SIGN': signature,
                        'X-BAPI-RECV-WINDOW': recv_window
                    }
                    request_headers.update(headers)
                
                response = self.session.post(url, data=payload, headers=request_headers, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return {"retCode": -1, "retMsg": str(e)}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse response: {e}")
            return {"retCode": -1, "retMsg": "Parse error"}
    
    def get_klines(self, symbol: str, interval: str, limit: int = 200) -> List[Dict]:
        """
        캔들 데이터 조회 (Public)
        """
        endpoint = "/v5/market/kline"
        params = {
            'category': 'linear',
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        # Public 요청으로 설정
        response = self._request('GET', endpoint, params, public=True)
        
        if response.get('retCode') == 0:
            return response.get('result', {}).get('list', [])
        else:
            logger.error(f"Failed to get klines: {response}")
            return []
    
    def get_ticker(self, symbol: str) -> Dict:
        """
        현재 시세 조회 (Public)
        """
        endpoint = "/v5/market/tickers"
        params = {
            'category': 'linear',
            'symbol': symbol
        }
        
        response = self._request('GET', endpoint, params, public=True)
        
        if response.get('retCode') == 0:
            tickers = response.get('result', {}).get('list', [])
            return tickers[0] if tickers else {}
        else:
            logger.error(f"Failed to get ticker: {response}")
            return {}
    
    def get_balance(self) -> Dict:
        """
        계좌 잔고 조회
        
        Returns:
            계좌 정보
        """
        endpoint = "/v5/account/wallet-balance"
        params = {'accountType': 'UNIFIED'}
        
        response = self._request('GET', endpoint, params)
        
        if response.get('retCode') == 0:
            return response.get('result', {})
        else:
            logger.error(f"Failed to get balance: {response}")
            return {}
    
    def get_positions(self, symbol: str) -> List[Dict]:
        """
        포지션 조회
        
        Args:
            symbol: 거래 심볼
        
        Returns:
            포지션 정보 리스트
        """
        endpoint = "/v5/position/list"
        params = {
            'category': 'linear',
            'symbol': symbol
        }
        
        response = self._request('GET', endpoint, params)
        
        if response.get('retCode') == 0:
            return response.get('result', {}).get('list', [])
        else:
            logger.error(f"Failed to get positions: {response}")
            return []
    
    def place_order(self, symbol: str, side: str, qty: float, price: Optional[float] = None,
                   order_type: str = 'Market', leverage: int = 1) -> Dict:
        """
        주문 생성
        
        Args:
            symbol: 거래 심볼
            side: 주문 방향 ('Buy' 또는 'Sell')
            qty: 주문 수량
            price: 주문 가격 (Market 주문 시 None)
            order_type: 주문 타입 ('Market' 또는 'Limit')
            leverage: 레버리지
        
        Returns:
            주문 정보
        """
        endpoint = "/v5/order/create"
        
        params = {
            'category': 'linear',
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'qty': str(qty),
            'leverage': str(leverage),
            'positionIdx': 0  # 양방향 포지션
        }
        
        if order_type == 'Limit' and price:
            params['price'] = str(price)
        
        response = self._request('POST', endpoint, params)
        
        if response.get('retCode') == 0:
            logger.info(f"Order placed: {response}")
            return response.get('result', {})
        else:
            logger.error(f"Failed to place order: {response}")
            return {}
    
    def close_position(self, symbol: str, side: str) -> Dict:
        """
        포지션 청산
        
        Args:
            symbol: 거래 심볼
            side: 청산 방향 ('Buy' 또는 'Sell')
        
        Returns:
            주문 정보
        """
        # 현재 포지션 조회
        positions = self.get_positions(symbol)
        
        if not positions:
            logger.warning(f"No position found for {symbol}")
            return {}
        
        position = positions[0]
        qty = float(position.get('size', 0))
        
        if qty == 0:
            logger.warning(f"Position size is 0 for {symbol}")
            return {}
        
        # 반대 방향으로 주문
        return self.place_order(symbol, side, qty, order_type='Market')
    
    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """
        주문 취소
        
        Args:
            symbol: 거래 심볼
            order_id: 주문 ID
        
        Returns:
            취소 결과
        """
        endpoint = "/v5/order/cancel"
        params = {
            'category': 'linear',
            'symbol': symbol,
            'orderId': order_id
        }
        
        response = self._request('POST', endpoint, params)
        
        if response.get('retCode') == 0:
            logger.info(f"Order cancelled: {order_id}")
            return response.get('result', {})
        else:
            logger.error(f"Failed to cancel order: {response}")
            return {}
    
    def set_leverage(self, symbol: str, leverage: int) -> Dict:
        """
        레버리지 설정
        
        Args:
            symbol: 거래 심볼
            leverage: 레버리지
        
        Returns:
            설정 결과
        """
        endpoint = "/v5/position/set-leverage"
        params = {
            'category': 'linear',
            'symbol': symbol,
            'buyLeverage': str(leverage),
            'sellLeverage': str(leverage)
        }
        
        response = self._request('POST', endpoint, params)
        
        if response.get('retCode') == 0:
            logger.info(f"Leverage set to {leverage} for {symbol}")
            return response.get('result', {})
        elif response.get('retCode') == 110012: # Leverage not changed
            return {}
        else:
            logger.error(f"Failed to set leverage: {response}")
            return {}

    def get_instrument_info(self, symbol: str) -> Dict:
        """
        심볼 정보 조회 (Public)
        """
        endpoint = "/v5/market/instruments-info"
        params = {
            'category': 'linear',
            'symbol': symbol
        }
        
        response = self._request('GET', endpoint, params, public=True)
        
        if response.get('retCode') == 0:
            info = response.get('result', {}).get('list', [])
            return info[0] if info else {}
        else:
            logger.error(f"Failed to get instrument info: {response}")
            return {}

    def set_trading_stop(self, symbol: str, side: str, sl_price: Optional[float] = None, tp_price: Optional[float] = None) -> Dict:
        """
        손절/익절 설정
        """
        endpoint = "/v5/position/trading-stop"
        params = {
            'category': 'linear',
            'symbol': symbol,
            'positionIdx': 0
        }
        
        if sl_price:
            params['stopLoss'] = str(sl_price)
        if tp_price:
            params['takeProfit'] = str(tp_price)
            
        response = self._request('POST', endpoint, params)
        
        if response.get('retCode') == 0:
            logger.info(f"Trading stop set: SL={sl_price}, TP={tp_price}")
            return response.get('result', {})
        else:
            logger.error(f"Failed to set trading stop: {response}")
            return {}
