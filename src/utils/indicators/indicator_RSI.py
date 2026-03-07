# indicator_RSI.py
# Vai trò: Tính toán Relative Strength Index (RSI)
import pandas as pd
import numpy as np


def calculate_rsi(close_prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using Wilder's smoothing (rolling mean approximation)."""
    delta = close_prices.diff()
    gains = delta.where(delta > 0, 0)
    losses = -delta.where(delta < 0, 0)
    avg_gains = gains.rolling(window=period).mean()
    avg_losses = losses.rolling(window=period).mean()
    rs = avg_gains / avg_losses
    rs = rs.replace([np.inf, -np.inf], np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi
