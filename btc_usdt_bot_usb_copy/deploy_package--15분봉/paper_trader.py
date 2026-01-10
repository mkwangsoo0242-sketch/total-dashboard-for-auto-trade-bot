import json
import os
import time
from datetime import datetime

class PaperTrader:
    def __init__(self, config, state_file='paper_trade_state.json'):
        self.config = config
        self.state_file = state_file
        self.balance = 100.0 # Default starting balance
        self.position = None
        self.trade_history = []
        self.load_state()

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.balance = data.get('balance', 100.0)
                    self.position = data.get('position', None)
                    self.trade_history = data.get('trade_history', [])
                print(f"Paper Trader Loaded: Balance=${self.balance:.2f}, Position={self.position}")
            except Exception as e:
                print(f"Error loading paper trade state: {e}")

    def save_state(self):
        data = {
            'balance': self.balance,
            'position': self.position,
            'trade_history': self.trade_history
        }
        try:
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving paper trade state: {e}")

    def open_position(self, signal, price, sl, tp):
        if self.position is not None:
            print("Position already open!")
            return

        leverage = self.config['exchange']['leverage']
        risk_per_trade = self.config['risk']['risk_per_trade_percent'] / 100.0
        
        # Calculate Position Size based on Risk
        # Loss = Entry - SL
        # Risk Amount = Balance * risk_per_trade
        # Size = Risk Amount / |Entry - SL|
        
        risk_amount = self.balance * risk_per_trade
        price_diff = abs(price - sl)
        
        if price_diff == 0:
            print("Invalid SL (Same as Entry)")
            return
            
        size = risk_amount / price_diff
        
        # Apply Leverage Limit
        max_size = (self.balance * leverage) / price
        size = min(size, max_size)
        
        self.position = {
            'entry_time': datetime.now().isoformat(),
            'side': signal,
            'entry_price': price,
            'amount': size,
            'stop_loss': sl,
            'take_profit': tp,
            'leverage': leverage
        }
        
        print(f"Paper Trade OPEN: {signal.upper()} @ {price} | Size: {size:.4f} | Risk: ${risk_amount:.2f}")
        self.save_state()

    def close_position(self, price, reason):
        if self.position is None:
            return

        pos = self.position
        side = pos['side']
        entry = pos['entry_price']
        amount = pos['amount']
        leverage = pos['leverage']
        
        # PnL Calculation
        if side == 'buy':
            pnl = (price - entry) * amount
        else:
            pnl = (entry - price) * amount
            
        # Fee Simulation (0.05% taker)
        fee = (price * amount * 0.0005) + (entry * amount * 0.0005)
        net_pnl = pnl - fee
        
        self.balance += net_pnl
        
        trade_record = {
            'entry_time': pos['entry_time'],
            'exit_time': datetime.now().isoformat(),
            'side': side,
            'entry_price': entry,
            'exit_price': price,
            'amount': amount,
            'pnl': net_pnl,
            'reason': reason,
            'balance_after': self.balance
        }
        
        self.trade_history.append(trade_record)
        self.position = None
        
        print(f"Paper Trade CLOSE: {reason} @ {price} | PnL: ${net_pnl:.2f} | New Balance: ${self.balance:.2f}")
        self.save_state()

    def update(self, current_price, current_rsi=None):
        """Check TP/SL or other exit conditions"""
        if self.position is None:
            return

        pos = self.position
        side = pos['side']
        sl = pos['stop_loss']
        tp = pos['take_profit']
        
        # Check SL/TP
        if side == 'buy':
            if current_price <= sl:
                self.close_position(sl, 'stop_loss')
            elif current_price >= tp:
                self.close_position(tp, 'take_profit')
        elif side == 'sell':
            if current_price >= sl:
                self.close_position(sl, 'stop_loss')
            elif current_price <= tp:
                self.close_position(tp, 'take_profit')
                
        # Trailing Stop (Optional)
        if self.config['strategy'].get('use_trailing_stop', False) and self.position is not None:
             # Logic to update SL would go here
             pass
