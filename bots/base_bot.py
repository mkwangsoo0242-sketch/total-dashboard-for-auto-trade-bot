import threading
import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime

class BaseBot(ABC):
    def __init__(self, name, interval):
        self.name = name
        self.interval = interval # e.g., '5m', '15m', '30m', '1h'
        self.is_running = False
        self.thread = None
        self.status = "Stopped"
        self.last_run = None
        
        # New monitoring fields
        self.current_balance = 0.0
        self.current_position = "None" # e.g., 'Long', 'Short', 'None'
        self.liquidation_price = 0.0
        self.liquidation_profit = 0.0
        self.total_roi = 0.0 # Total Return on Investment (%)
        self.balance_history = [] # Historical balance for graphing
        self.max_history = 50 # Maximum data points to keep
        self.recent_candles = [] # OHLCV data for charting: [{'t': timestamp, 'o': open, 'h': high, 'l': low, 'c': close}, ...]
        
        # Setup logging
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def start(self):
        if self.is_running:
            self.logger.warning(f"{self.name} is already running.")
            return
        
        self.is_running = True
        self.status = "Running"
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"{self.name} started.")

    def stop(self):
        if not self.is_running:
            self.logger.warning(f"{self.name} is already stopped.")
            return
        
        self.is_running = False
        self.status = "Stopping"
        self.logger.info(f"{self.name} stopping...")

    def _run_loop(self):
        while self.is_running:
            try:
                self.last_run = datetime.now()
                self.execute_logic()
                # Interval handling (simplified for this template)
                self._wait_for_next_tick()
            except Exception as e:
                self.logger.error(f"Error in {self.name}: {str(e)}")
                self.status = "Error"
                time.sleep(10) # Wait before retry

        self.status = "Stopped"
        self.logger.info(f"{self.name} stopped.")

    @abstractmethod
    def execute_logic(self):
        """This method should be implemented by subclasses to perform the actual trading logic."""
        pass

    def _wait_for_next_tick(self):
        # Convert interval string to seconds
        seconds = self._interval_to_seconds(self.interval)
        time.sleep(seconds)

    def _interval_to_seconds(self, interval):
        unit = interval[-1]
        value = int(interval[:-1])
        if unit == 's':
            return value
        elif unit == 'm':
            return value * 60
        elif unit == 'h':
            return value * 3600
        elif unit == 'd':
            return value * 86400
        return 60
