# test_indicators.py
# Unit test cho tất cả indicator trong utils/indicators/
# Chạy: pytest tests/test_indicators.py

import pandas as pd
import numpy as np
import pytest

from src.utils.indicators.MA import calculate_sma, calculate_ema
from src.utils.indicators.MACD import calculate_macd
from src.utils.indicators.ATR import calculate_atr
from src.utils.indicators.RSI import calculate_rsi


def make_sample_df(n=100):
    """Tạo DataFrame nến giả để test"""
    np.random.seed(42)
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    high = close + np.abs(np.random.randn(n)) * 0.5
    low = close - np.abs(np.random.randn(n)) * 0.5
    return close, high, low


class TestMA:
    def test_sma_length(self):
        close, _, _ = make_sample_df()
        result = calculate_sma(close, period=20)
        assert len(result) == len(close)

    def test_ema_length(self):
        close, _, _ = make_sample_df()
        result = calculate_ema(close, period=20)
        assert len(result) == len(close)


class TestMACD:
    def test_macd_returns_three_series(self):
        close, _, _ = make_sample_df()
        macd, signal, hist = calculate_macd(close)
        assert len(macd) == len(close)
        assert len(signal) == len(close)
        assert len(hist) == len(close)


class TestATR:
    def test_atr_length(self):
        close, high, low = make_sample_df()
        result = calculate_atr(high, low, close, period=5)
        assert len(result) == len(close)


class TestRSI:
    def test_rsi_range(self):
        close, _, _ = make_sample_df()
        result = calculate_rsi(close, period=14).dropna()
        assert (result >= 0).all() and (result <= 100).all()
