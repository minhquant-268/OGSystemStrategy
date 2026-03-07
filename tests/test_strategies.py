# test_strategies.py
# Unit test cho tất cả strategy trong src/strategies/
# Chạy: pytest tests/test_strategies.py

import pandas as pd
import numpy as np
import pytest


def make_candle_df(n=200):
    """Tạo DataFrame nến giả để test strategy"""
    np.random.seed(42)
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    high = close + np.abs(np.random.randn(n)) * 0.5
    low = close - np.abs(np.random.randn(n)) * 0.5
    open_ = close.shift(1).fillna(close.iloc[0])
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": np.random.randint(100, 1000, n),
        "time": pd.date_range("2025-01-01", periods=n, freq="15min"),
        "timestampMs": pd.date_range("2025-01-01", periods=n, freq="15min").astype(int) // 10**6
    })


# TODO: Uncomment khi strategy đã được implement
# from src.strategies.strategy_comboATR import ComboATRStrategy
# from src.strategies.strategy_MAcrossover import MACrossoverStrategy
#
# class TestComboATR:
#     def test_signal_column_exists(self):
#         strategy = ComboATRStrategy()
#         df = make_candle_df()
#         result = strategy.calculate_signals(df)
#         assert "signal" in result.columns
#
#     def test_signal_values_valid(self):
#         strategy = ComboATRStrategy()
#         df = make_candle_df()
#         result = strategy.calculate_signals(df)
#         assert result["signal"].isin([0, 1, 2]).all()
