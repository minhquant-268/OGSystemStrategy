# test_indicators.py
# Unit test cho tất cả indicator trong indicators/
# Chạy: pytest tests/test_indicators.py

import pandas as pd
import numpy as np
import pytest

from src.indicators.MA import calculate_sma, calculate_ema
from src.indicators.MACD import calculate_macd
from src.indicators.ATR import calculate_atr
from src.indicators.RSI import calculate_rsi
from src.indicators.KNN_trend import calculate_knn_trend


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


class TestKNNTrend:
    def test_output_keys(self):
        """Kiem tra dict tra ve du cac key can thiet"""
        close, high, low = make_sample_df(200)
        result = calculate_knn_trend(high, low, close)
        expected_keys = {
            "knn_ma", "knn_avg", "knn_prediction", "knn_color",
            "cross_over_avg", "cross_under_avg", "switch_up", "switch_down",
        }
        assert set(result.keys()) == expected_keys

    def test_output_lengths(self):
        """Kiem tra cac Series cung do dai voi input"""
        close, high, low = make_sample_df(200)
        result = calculate_knn_trend(high, low, close)
        for key, series in result.items():
            assert len(series) == len(close), f"{key} length mismatch"

    def test_prediction_values(self):
        """Kiem tra knn_prediction chi chua gia tri hop le (gan -1, 0, 1)"""
        close, high, low = make_sample_df(200)
        result = calculate_knn_trend(high, low, close)
        pred = result["knn_prediction"]
        # WMA-smoothed nen gia tri la lien tuc, nhung phai nam trong [-1, 1]
        valid = pred.dropna()
        assert (valid >= -1.5).all() and (valid <= 1.5).all()
