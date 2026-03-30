"""
indicator_MA.py
===============
Moving Average indicators: SMA va EMA.

Ham xuat (public API):
    calculate_sma(close, period) -> pd.Series
    calculate_ema(close, period) -> pd.Series

Duoc dung boi:
    indicator_MACD.py     (EMA fast/slow de tinh MACD line)
    indicator_ADX.py      (EMA-based Wilder smoothing)
    strategy_comboATR.py  (SMA lam filter trend)
    strategy_MAcrossover.py (EMA fast/slow crossover)
"""

import pandas as pd


def calculate_sma(close_prices: pd.Series, period: int = 20) -> pd.Series:
    """
    Simple Moving Average (SMA).
    TB bieu so don gian cua `period` nen gan nhat.

    Args:
        close_prices : pd.Series gia dong cua nen
        period       : Cua so tinh trung binh (mac dinh 20)

    Returns:
        pd.Series cung index voi close_prices.
        `period - 1` gia tri dau la NaN (chua du du lieu).

    Vi du:
        sma20 = calculate_sma(df["close"], period=20)
    """
    return close_prices.rolling(window=period).mean()


def calculate_ema(close_prices: pd.Series, period: int = 20) -> pd.Series:
    """
    Exponential Moving Average (EMA).
    Cach tinh: EMA = Price * k + EMA_prev * (1 - k), voi k = 2 / (period + 1)
    Su dung ewm(span=period, adjust=False) cua pandas.

    Args:
        close_prices : pd.Series gia dong (hoac bat ky series gia tri lien tuc)
        period       : Chu ky EMA (mac dinh 20)

    Returns:
        pd.Series EMA, cung do dai voi input (khong co NaN dau).

    Vi du:
        ema5  = calculate_ema(df["close"], period=5)
        ema25 = calculate_ema(df["close"], period=25)
    """
    return close_prices.ewm(span=period, adjust=False).mean()
