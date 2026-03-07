# indicator_MACD.py
# Vai trò: Tính toán MACD (Moving Average Convergence Divergence)
# Trả về: MACD line, Signal line, Histogram
import pandas as pd
from utils.indicators.indicator_MA import calculate_ema


def calculate_macd(
    close_prices: pd.Series,
    fast_period: int = 5,
    slow_period: int = 25,
    signal_period: int = 5
):
    """
    Calculate MACD, Signal line, and Histogram.
    Returns: (macd, signal, histogram) - mỗi cái là pd.Series
    """
    ema_fast = calculate_ema(close_prices, fast_period)
    ema_slow = calculate_ema(close_prices, slow_period)
    macd = ema_fast - ema_slow
    signal = calculate_ema(macd, signal_period)
    hist = macd - signal
    return macd, signal, hist
