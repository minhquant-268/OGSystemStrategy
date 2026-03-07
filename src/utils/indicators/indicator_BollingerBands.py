# indicator_BollingerBands.py
# Vai trò: Tính toán Bollinger Bands (Upper, Middle, Lower)
import pandas as pd


def calculate_bollinger_bands(
    close_prices: pd.Series,
    period: int = 20,
    std_dev: float = 2.0
):
    """
    Calculate Bollinger Bands.
    Returns: (upper_band, middle_band, lower_band) - mỗi cái là pd.Series
    """
    middle = close_prices.rolling(window=period).mean()
    std = close_prices.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower
