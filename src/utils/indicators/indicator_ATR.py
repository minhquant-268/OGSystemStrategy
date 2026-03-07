# indicator_ATR.py
# Vai trò: Tính toán Average True Range (ATR)
# Dùng để tính SL/TP động trong strategy comboATR
import pandas as pd
import numpy as np


def calculate_atr(
    high_prices: pd.Series,
    low_prices: pd.Series,
    close_prices: pd.Series,
    period: int = 5
) -> pd.Series:
    """
    Calculate ATR using Wilder's smoothing method.
    ATR = ((ATR_prev * (n-1)) + TR) / n
    """
    high_low = high_prices - low_prices
    high_close = np.abs(high_prices - close_prices.shift(1))
    low_close = np.abs(low_prices - close_prices.shift(1))
    tr = pd.DataFrame({"hl": high_low, "hc": high_close, "lc": low_close}).max(axis=1)

    atr = np.zeros(len(tr))
    atr[0] = tr.iloc[0] if not np.isnan(tr.iloc[0]) else 0
    for i in range(1, len(tr)):
        if not np.isnan(tr.iloc[i]):
            atr[i] = ((atr[i - 1] * (period - 1)) + tr.iloc[i]) / period
        else:
            atr[i] = atr[i - 1]
    return pd.Series(atr, index=tr.index)
