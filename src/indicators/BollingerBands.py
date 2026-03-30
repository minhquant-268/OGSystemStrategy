"""
indicator_BollingerBands.py
============================
Bollinger Bands - dai bien dong gia xung quanh duong MA.

Ham xuat (public API):
    calculate_bollinger_bands(close, period, std_dev) -> (upper, middle, lower)
    calculate_bb_percent_b(close, upper, lower)       -> pd.Series   [bonus]
    calculate_bb_bandwidth(upper, middle, lower)      -> pd.Series   [bonus]

Cong thuc:
    Middle = SMA(close, period)
    Upper  = Middle + std_dev * StdDev(close, period)
    Lower  = Middle - std_dev * StdDev(close, period)

    %B = (close - lower) / (upper - lower)   -> [0,1] binh thuong, >1 qua mua, <0 qua ban
    Bandwidth = (upper - lower) / middle     -> do rong dai, nho = bien dong thap

Duoc dung boi:
    strategy_comboATR.py (tuy chon: loc tin hieu khi gia cham band tren/duoi)
"""

import pandas as pd


def calculate_bollinger_bands(
    close_prices: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Tinh Bollinger Bands (Upper, Middle, Lower).

    Args:
        close_prices : pd.Series gia dong
        period       : Cua so SMA va StdDev (mac dinh 20)
        std_dev      : So lan do lech chuan (mac dinh 2.0)

    Returns:
        Tuple (upper, middle, lower) - moi gia tri la pd.Series cung index voi input.
        `period - 1` gia tri dau la NaN.

    Vi du:
        upper, mid, lower = calculate_bollinger_bands(df["close"], period=20, std_dev=2.0)
        df["BB_upper"]  = upper
        df["BB_middle"] = mid
        df["BB_lower"]  = lower

        # Tin hieu: gia cham band tren -> qua mua
        touch_upper = df["close"] >= upper
        touch_lower = df["close"] <= lower
    """
    middle = close_prices.rolling(window=period).mean()
    std    = close_prices.rolling(window=period).std(ddof=1)   # ddof=1: sample std (chuan thong ke)
    upper  = middle + std_dev * std
    lower  = middle - std_dev * std
    return upper.rename("BB_upper"), middle.rename("BB_middle"), lower.rename("BB_lower")


def calculate_bb_percent_b(
    close_prices: pd.Series,
    upper: pd.Series,
    lower: pd.Series,
) -> pd.Series:
    """
    Tinh %B: vi tri gia trong Bollinger Bands.
    %B = (close - lower) / (upper - lower)
    
    Y nghia:
        %B = 1.0  : gia dung tren upper band
        %B = 0.5  : gia o giua
        %B = 0.0  : gia dung tren lower band
        %B > 1.0  : gia thoat khoi upper band (qua mua manh)
        %B < 0.0  : gia thoat khoi lower band (qua ban manh)

    Returns:
        pd.Series %B (float, co the out-of-range [0,1])
    """
    band_width = upper - lower
    # Tranh chia cho 0 khi band_width = 0 (gia khong bien dong)
    percent_b  = (close_prices - lower) / band_width.replace(0, float("nan"))
    return percent_b.rename("BB_pctB")


def calculate_bb_bandwidth(
    upper: pd.Series,
    middle: pd.Series,
    lower: pd.Series,
) -> pd.Series:
    """
    Tinh Bandwidth: do rong tuong doi cua Bollinger Bands.
    Bandwidth = (upper - lower) / middle

    Y nghia:
        Bandwidth nho: bien dong thap, thi truong dang tich luy
        Bandwidth tang dot bien: co the xuat hien breakout
        Thuong dung ket hop voi Bollinger Squeeze (Bandwidth < nguong)

    Returns:
        pd.Series Bandwidth (float, khong co don vi)
    """
    bandwidth = (upper - lower) / middle.replace(0, float("nan"))
    return bandwidth.rename("BB_bandwidth")
