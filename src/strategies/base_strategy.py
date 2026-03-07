# base_strategy.py
# Vai trò: Abstract base class cho tất cả strategy trong hệ thống
# Mọi strategy mới PHẢI kế thừa BaseStrategy và implement các method này.
#
# Contract bắt buộc:
#   - calculate_signals(df: pd.DataFrame) -> pd.DataFrame
#       Nhận DataFrame nến chuẩn, trả về DataFrame có thêm cột:
#       'signal' (int), 'entry', 'sl', 'tp', 'sl_distance', 'tp_distance'
#
#   - get_indicators(df: pd.DataFrame) -> dict
#       Trả về dict các indicator để dashboard vẽ chart (tùy chọn)

import pandas as pd


class BaseStrategy:
    def __init__(self):
        self.name = "BaseStrategy"

    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Tính toán tín hiệu giao dịch dựa trên DataFrame nến đầu vào.
        Phải được override ở subclass.
        """
        raise NotImplementedError("Subclasses must implement calculate_signals()")

    def get_indicators(self, df: pd.DataFrame) -> dict:
        """
        Trả về dict các indicator để dashboard vẽ chart.
        Tùy chọn, có thể override ở subclass.
        """
        return {}
