"""
indicator_ADX.py
================
ADX (Average Directional Index) + DI+ / DI-
Do luong STC MANH cua xu huong (khong phan biet huong len hay xuong).

Ham xuat (public API):
    calculate_adx(high, low, close, period) -> (adx, plus_di, minus_di)

Cong thuc (Wilder's method):
    TR       = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    +DM      = up_move  neu up_move > down_move va up_move > 0, else 0
    -DM      = down_move neu down_move > up_move va down_move > 0, else 0
    TR_smooth   = EMA(TR,   alpha=1/period)
    +DM_smooth  = EMA(+DM,  alpha=1/period)
    -DM_smooth  = EMA(-DM,  alpha=1/period)
    +DI = 100 * +DM_smooth / TR_smooth
    -DI = 100 * -DM_smooth / TR_smooth
    DX  = 100 * |+DI - -DI| / (+DI + -DI)
    ADX = EMA(DX, alpha=1/period)

Y nghia:
    ADX < 20 : Xu huong yeu hoac di ngang
    ADX > 25 : Xu huong ro rang (manh)
    ADX > 50 : Xu huong rat manh
    +DI > -DI: Xu huong tang
    -DI > +DI: Xu huong giam

Duoc dung boi:
    strategy_comboATR.py (tuy chon: chi vao lenh khi ADX > 25)
"""

import pandas as pd
import numpy as np


def calculate_adx(
    high_prices: pd.Series,
    low_prices: pd.Series,
    close_prices: pd.Series,
    period: int = 14,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Tinh ADX, DI+ va DI- theo phuong phap Wilder.

    Args:
        high_prices  : pd.Series gia cao nhat
        low_prices   : pd.Series gia thap nhat
        close_prices : pd.Series gia dong
        period       : Chu ky Wilder smoothing (mac dinh 14)

    Returns:
        Tuple (adx, plus_di, minus_di):
            adx      : ADX Series [0..100], cang cao xu huong cang manh
            plus_di  : +DI Series [0..100]
            minus_di : -DI Series [0..100]
        Gia tri NaN dau duoc fill thanh 0.0 de tranh loi tinh toan o strategy.

    Vi du:
        adx, plus_di, minus_di = calculate_adx(df["high"], df["low"], df["close"], period=14)
        strong_trend = adx > 25          # Bool Series
        uptrend      = plus_di > minus_di
        downtrend    = minus_di > plus_di
    """
    high  = pd.Series(high_prices.values,  index=high_prices.index,  dtype=float)
    low   = pd.Series(low_prices.values,   index=low_prices.index,   dtype=float)
    close = pd.Series(close_prices.values, index=close_prices.index, dtype=float)

    # True Range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Directional Movement
    up_move   = high.diff()
    down_move = -low.diff()

    plus_dm  = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move

    # Wilder smoothing: ewm voi alpha = 1/period, adjust=False
    alpha = 1.0 / period
    tr_smooth       = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_dm_smooth  = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=alpha, adjust=False).mean()

    # DI+ / DI-
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di  = 100.0 * plus_dm_smooth  / tr_smooth
        minus_di = 100.0 * minus_dm_smooth / tr_smooth

    # DX va ADX
    denom = (plus_di + minus_di).replace(0.0, np.nan)
    dx    = 100.0 * (plus_di - minus_di).abs() / denom
    adx   = dx.ewm(alpha=alpha, adjust=False).mean()

    # Fill NaN dau voi 0.0 (chinh sach nhat quan voi cac indicator khac)
    plus_di  = plus_di.fillna(0.0).rename("DI_plus")
    minus_di = minus_di.fillna(0.0).rename("DI_minus")
    adx      = adx.fillna(0.0).rename("ADX")

    return adx, plus_di, minus_di
