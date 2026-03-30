"""
indicator_RSI.py
================
RSI (Relative Strength Index) - chi bao dong luc/qua mua/qua ban.

Ham xuat (public API):
    calculate_rsi(close, period) -> pd.Series

Cong thuc:
    delta     = close.diff()
    gain      = max(delta, 0)
    loss      = max(-delta, 0)
    avg_gain  = SMA(gain, period)     # xap xi Wilder smoothing
    avg_loss  = SMA(loss, period)
    RS        = avg_gain / avg_loss
    RSI       = 100 - (100 / (1 + RS))

Nguong hay dung:
    RSI > 70 : Qua mua (overbought) -> xem xet SELL
    RSI < 30 : Qua ban (oversold)   -> xem xet BUY
    RSI = 50 : Duong trung tinh

Duoc dung boi:
    strategy_comboATR.py (bo loc RSI: chi SELL khi RSI > 70, chi BUY khi RSI < 30)
"""

import pandas as pd
import numpy as np


def calculate_rsi(close_prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Tinh RSI (Relative Strength Index).

    Su dung rolling mean (SMA) lam xap xi Wilder smoothing.
    Ket qua kha sat voi TA-Lib va TradingView cho cac dataset dai.

    Args:
        close_prices : pd.Series gia dong cua nen
        period       : Chu ky RSI (mac dinh 14)

    Returns:
        pd.Series RSI trong khoang [0, 100].
        `period` gia tri dau la NaN (chua du du lieu de tinh).
        Gia tri NaN khi avg_loss=0 (chi tang, khong co phien giam) duoc xu ly
        thanh 100.0 tu dong boi cong thuc (1/0 -> inf -> RSI = 100).

    Vi du:
        rsi14 = calculate_rsi(df["close"], period=14)
        overbought  = rsi14 > 70   # pd.Series bool
        oversold    = rsi14 < 30
    """
    close_prices = pd.Series(close_prices.values, index=close_prices.index, dtype=float)
    delta  = close_prices.diff()
    gains  = delta.where(delta > 0, 0.0)
    losses = (-delta).where(delta < 0, 0.0)

    avg_gains  = gains.rolling(window=period).mean()
    avg_losses = losses.rolling(window=period).mean()

    rs  = avg_gains / avg_losses
    rs  = rs.replace([np.inf, -np.inf], np.nan)   # avg_losses = 0 -> inf -> handle
    rsi = 100.0 - (100.0 / (1.0 + rs))

    return rsi.rename("RSI")
