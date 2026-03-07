"""
indicator_MACD.py
=================
MACD (Moving Average Convergence Divergence).

Ham xuat (public API):
    calculate_macd(close, fast, slow, signal) -> (macd, signal, hist)

MACD la chi bao dong luc (momentum), do khoang cach giua 2 EMA.
    MACD line   = EMA(fast) - EMA(slow)
    Signal line = EMA(MACD line, signal_period)
    Histogram   = MACD line - Signal line

Gia tri mac dinh phu hop voi he thong ComboATR:
    fast=5, slow=25, signal=5

Duoc dung boi:
    strategy_comboATR.py (MACD crossover lam tin hieu chinh)
"""

import pandas as pd
from src.utils.indicators.MA import calculate_ema


def calculate_macd(
    close_prices: pd.Series,
    fast_period: int = 5,
    slow_period: int = 25,
    signal_period: int = 5,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Tinh MACD, Signal line va Histogram.

    Args:
        close_prices  : pd.Series gia dong
        fast_period   : Chu ky EMA nhanh (mac dinh 5)
        slow_period   : Chu ky EMA cham (mac dinh 25)
        signal_period : Chu ky EMA cua MACD line (mac dinh 5)

    Returns:
        Tuple (macd, signal, hist) - moi gia tri la pd.Series cung index voi input.
        macd   : MACD line = EMA(fast) - EMA(slow)
        signal : Signal line = EMA(macd, signal_period)
        hist   : Histogram = macd - signal (duong khi MACD > Signal)

    Vi du:
        macd, signal, hist = calculate_macd(df["close"], fast_period=5, slow_period=25, signal_period=5)
        df["MACD"]      = macd
        df["MACD_Signal"] = signal
        df["MACD_Hist"] = hist
    """
    ema_fast = calculate_ema(close_prices, fast_period)
    ema_slow = calculate_ema(close_prices, slow_period)
    macd     = ema_fast - ema_slow
    signal   = calculate_ema(macd, signal_period)
    hist     = macd - signal
    return macd, signal, hist
