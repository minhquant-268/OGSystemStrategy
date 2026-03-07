# indicator_MA.py
# Vai trò: Tính toán Moving Average (SMA, EMA, WMA)
# Dùng chung cho tất cả strategy cần MA
import pandas as pd


def calculate_sma(close_prices: pd.Series, period: int = 20) -> pd.Series:
    """Simple Moving Average"""
    return close_prices.rolling(window=period).mean()


def calculate_ema(close_prices: pd.Series, period: int = 20) -> pd.Series:
    """Exponential Moving Average"""
    return close_prices.ewm(span=period, adjust=False).mean()
