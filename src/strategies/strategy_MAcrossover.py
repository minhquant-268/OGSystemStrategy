# strategy_MAcrossover.py
# Vai trò: Strategy MA Crossover
# Kế thừa BaseStrategy, implement calculate_signals()
# Logic: Tạo tín hiệu BUY/SELL dựa trên giao cắt giữa 2 đường Moving Average

from src.strategies.base_strategy import BaseStrategy
import pandas as pd


class MACrossoverStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "MAcrossover"

    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # TODO: implement MA crossover logic
        # Sử dụng utils/indicators/indicator_MA.py để tính MA
        raise NotImplementedError

    def get_indicators(self, df: pd.DataFrame) -> dict:
        return {}
