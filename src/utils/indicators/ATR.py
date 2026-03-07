"""
indicator_ATR.py
================
ATR (Average True Range) - do luong bien dong gia.

Ham xuat (public API):
    calculate_atr(high, low, close, period) -> pd.Series

True Range (TR) = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
ATR Wilder's smoothing: ATR[i] = (ATR[i-1] * (n-1) + TR[i]) / n

Wilder's smoothing KHAC voi EMA thong thuong:
    - EMA dung multiplier k = 2/(n+1)
    - Wilder dung k = 1/n     (lam on hon, it nhay cam hon)

Duoc dung boi:
    strategy_comboATR.py (tinh SL/TP dong: sl = entry - multiplier * ATR)
"""

import pandas as pd
import numpy as np


def calculate_atr(
    high_prices: pd.Series,
    low_prices: pd.Series,
    close_prices: pd.Series,
    period: int = 5,
) -> pd.Series:
    """
    Tinh ATR (Average True Range) bang Wilder's smoothing.

    Args:
        high_prices  : pd.Series gia cao nhat cua moi nen
        low_prices   : pd.Series gia thap nhat cua moi nen
        close_prices : pd.Series gia dong cua nen
        period       : Chu ky Wilder (mac dinh 5 cho scalping, thuong dung 14)

    Returns:
        pd.Series ATR, cung index voi input.
        Gia tri dau (index=0) = TR[0], cac gia tri sau duoc lam on dan.
        Khong co NaN (khac voi rolling mean).

    Vi du:
        atr5 = calculate_atr(df["high"], df["low"], df["close"], period=5)
        df["SL"] = df["close"] - 1.5 * atr5   # SL = 1.5x ATR tu entry
        df["TP"] = df["close"] + 3.0 * atr5   # TP = 3.0x ATR tu entry
    """
    high_prices  = pd.Series(high_prices.values,  index=high_prices.index, dtype=float)
    low_prices   = pd.Series(low_prices.values,   index=low_prices.index,  dtype=float)
    close_prices = pd.Series(close_prices.values, index=close_prices.index, dtype=float)

    # True Range
    high_low   = high_prices - low_prices
    high_close = (high_prices - close_prices.shift(1)).abs()
    low_close  = (low_prices  - close_prices.shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    # Wilder's smoothing (loop-based vi ewm voi alpha=1/period cho ket qua khac)
    atr = np.zeros(len(tr))
    atr[0] = tr.iloc[0] if not np.isnan(tr.iloc[0]) else 0.0

    for i in range(1, len(tr)):
        tr_i = tr.iloc[i]
        if not np.isnan(tr_i):
            atr[i] = (atr[i - 1] * (period - 1) + tr_i) / period
        else:
            atr[i] = atr[i - 1]   # nen loi: giua nguyen ATR truoc do

    return pd.Series(atr, index=tr.index, name="ATR")
