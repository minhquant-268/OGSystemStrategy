# strategy_comboATR.py
# Vai trò: Strategy Combo ATR
# Kế thừa BaseStrategy, implement calculate_signals()
# Logic: Kết hợp MACD + SMA + ATR để xác định điểm vào lệnh + tính SL/TP động

from src.strategies.base_strategy import BaseStrategy
import pandas as pd


class ComboATRStrategy(BaseStrategy):
    def __init__(self, macd_fast=5, macd_slow=25, macd_signal=5, sma_period=20, atr_period=5):
        super().__init__()
        self.name = "comboATR"
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.sma_period = sma_period
        self.atr_period = atr_period

    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # TODO: implement Combo ATR logic
        # Sử dụng utils/indicators/indicator_MACD.py, indicator_MA.py, indicator_ATR.py
        raise NotImplementedError

    def get_indicators(self, df: pd.DataFrame) -> dict:
        return {}
