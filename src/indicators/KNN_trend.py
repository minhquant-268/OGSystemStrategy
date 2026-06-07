"""
KNN_trend.py
============
KNN Trend Navigator — chi bao xu huong dua tren thuat toan K-Nearest Neighbors.
Port tu PineScript "AI Trend Navigator" cua Zeiierman.

Ham xuat (public API):
    calculate_knn_trend(high, low, close, ...) -> dict[str, pd.Series]

==============================================================================
LOGIC TONG QUAT (cach hoat dong):
==============================================================================

1. TINH PRICE VALUE (value_in):
   - Lay gia theo phuong phap duoc chon (hl2, sma, ema, wma, hma).
   - Ap dung MA voi `ma_len` de lam muot.

2. TINH TARGET VALUE (target_in):
   - Lay gia muc tieu theo phuong phap khac (rma, sma, ema, wma, hma, atr).
   - Ap dung MA voi `target_ma_len`.

3. KNN MOVING AVERAGE (meanOfKClosest):
   - Voi moi nen hien tai, duyet `windowSize = max(n_neighbors, 30)` nen qua khu.
   - Tim `n_neighbors` gia tri value co khoang cach nho nhat den target hien tai:
       distance = |target_hien_tai - value[i]|
   - Lay trung binh cong cua `n_neighbors` gia tri gan nhat -> knn_ma_raw.
   - Smooth bang WMA(5) -> knn_ma (duong xu huong chinh).

4. KNN PREDICTION (classifier phan loai xu huong):
   - price = trung binh (knn_ma, close)
   - c = RMA(knn_ma[1], smoothing_period)   (gia tri "close" cua KNN candle)
   - o = RMA(knn_ma, smoothing_period)       (gia tri "open" cua KNN candle)
   - Voi moi nen, duyet 10 nen truoc:
       + Tim nen co distance nho nhat: sqrt((price[j] - price)^2)
       + Tai nen gan nhat do, neu c < o => Pos_count + 1, neu c > o => Neg_count + 1
   - Ket qua: Pos_count > Neg_count => +1 (bullish), nguoc lai => -1 (bearish)
   - Smooth bang WMA(3).

5. KNN AVERAGE LINE:
   - knn_avg = RMA(knn_ma_raw, smoothing_period)
   - Day la duong trung binh cham, dung de xac dinh crossover/crossunder.

6. TIN HIEU (Signals):
   - cross_over_avg  : knn_ma cat len knn_avg  (tin hieu mua)
   - cross_under_avg : knn_ma cat xuong knn_avg (tin hieu ban)
   - switch_up       : knn_ma bat dau tang (tu giam/di ngang sang tang)
   - switch_down     : knn_ma bat dau giam (tu tang/di ngang sang giam)
   - knn_color       : 1 = Up, -1 = Down, 0 = Neutral

==============================================================================
CACH SU DUNG TRONG STRATEGY:
==============================================================================

    from src.indicators.KNN_trend import calculate_knn_trend

    result = calculate_knn_trend(
        high  = df["high"],
        low   = df["low"],
        close = df["close"],
        price_method   = "hl2",    # phuong phap tinh gia
        target_method  = "rma",    # phuong phap tinh target
        ma_len         = 5,        # chu ky MA cho price
        target_ma_len  = 5,        # chu ky MA cho target
        n_neighbors    = 3,        # so neighbors KNN (cang cao cang muot)
        smoothing_period = 50,     # chu ky smooth (cang cao cang cham)
    )

    # --- Lay cac gia tri ---
    knn_ma         = result["knn_ma"]           # Duong xu huong chinh
    knn_avg        = result["knn_avg"]          # Duong trung binh cham
    knn_prediction = result["knn_prediction"]   # 1 = bullish, -1 = bearish

    # --- Tin hieu giao dich ---
    buy_signal  = result["cross_over_avg"]      # knn_ma cat len knn_avg
    sell_signal = result["cross_under_avg"]      # knn_ma cat xuong knn_avg
    trend_up    = result["switch_up"]            # Bat dau tang
    trend_down  = result["switch_down"]          # Bat dau giam

    # --- Ket hop voi dieu kien khac ---
    # Chi BUY khi knn_prediction = 1 VA knn_ma cat len knn_avg:
    strong_buy  = (knn_prediction > 0) & result["cross_over_avg"]
    # Chi SELL khi knn_prediction = -1 VA knn_ma cat xuong knn_avg:
    strong_sell = (knn_prediction < 0) & result["cross_under_avg"]

    # --- Su dung knn_color de biet trang thai hien tai ---
    # knn_color = 1 : dang tang (Up)
    # knn_color = 0 : trung tinh (Neutral)
    # knn_color = -1: dang giam (Down)

Duoc dung boi:
    src/core/signal_filter.py  (tich hop vao KNN filter pipeline)
"""

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Helper: Moving Averages
# ---------------------------------------------------------------------------

def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _wma(series: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average — trong so tang dan theo thoi gian."""
    weights = np.arange(1, period + 1, dtype=float)

    def _apply(x):
        return np.dot(x, weights) / weights.sum()

    return series.rolling(window=period, min_periods=period).apply(_apply, raw=True)


def _hma(series: pd.Series, period: int) -> pd.Series:
    """Hull Moving Average = WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    half = max(int(period / 2), 1)
    sqrt_p = max(int(np.sqrt(period)), 1)
    wma_half = _wma(series, half)
    wma_full = _wma(series, period)
    return _wma(2 * wma_half - wma_full, sqrt_p)


def _rma(series: pd.Series, period: int) -> pd.Series:
    """Running Moving Average (Wilder smoothing) = EMA voi alpha = 1/period."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return _rma(tr, period)


# ---------------------------------------------------------------------------
# Helper: chon phuong phap tinh MA
# ---------------------------------------------------------------------------

def _get_price_value(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    method: str,
    period: int,
) -> pd.Series:
    """
    Tinh Price Value (value_in) tu PineScript.

    - "hl2" : SMA( (high+low)/2, period )
    - "sma" : SMA(close, period)
    - "ema" : EMA(close, period)
    - "wma" : WMA(close, period)
    - "hma" : HMA(close, period)
    """
    method = method.lower().strip()
    if method == "hl2":
        return _sma((high + low) / 2.0, period)
    elif method == "sma":
        return _sma(close, period)
    elif method == "ema":
        return _ema(close, period)
    elif method == "wma":
        return _wma(close, period)
    elif method == "hma":
        return _hma(close, period)
    else:
        raise ValueError(f"price_method khong hop le: '{method}'. Chon: hl2, sma, ema, wma, hma")


def _get_target_value(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    method: str,
    period: int,
) -> pd.Series:
    """
    Tinh Target Value (target_in) tu PineScript.

    - "rma" : RMA(close, period)        (Price Action mac dinh)
    - "sma" : SMA(close, period)
    - "ema" : EMA(close, period)
    - "wma" : WMA(close, period)
    - "hma" : HMA(close, period)
    - "atr" : ATR(14)
    """
    method = method.lower().strip()
    if method in ("rma", "price_action"):
        return _rma(close, period)
    elif method == "sma":
        return _sma(close, period)
    elif method == "ema":
        return _ema(close, period)
    elif method == "wma":
        return _wma(close, period)
    elif method == "hma":
        return _hma(close, period)
    elif method in ("atr", "volatility"):
        return _atr(high, low, close, 14)
    else:
        raise ValueError(f"target_method khong hop le: '{method}'. Chon: rma, sma, ema, wma, hma, atr")


# ---------------------------------------------------------------------------
# Core: KNN Moving Average (meanOfKClosest)
# ---------------------------------------------------------------------------

def _mean_of_k_closest(
    value_arr: np.ndarray,
    target_arr: np.ndarray,
    n_neighbors: int,
    window_size: int,
) -> np.ndarray:
    """
    Voi moi vi tri i, duyet `window_size` nen truoc do,
    tim `n_neighbors` gia tri value[i-j] gan target[i] nhat (theo |target[i] - value[i-j]|),
    lay trung binh cong cua chung.

    Port chinh xac tu PineScript:
        meanOfKClosest(value_, target_) =>
            for i = 1 to windowSize
                value = value_[i]
                distance = abs(target_ - value)
                ... tim n_neighbors nho nhat ...
            closestValues.sum() / numberOfClosestValues
    """
    n = len(value_arr)
    result = np.full(n, np.nan)

    for i in range(window_size, n):
        # Khoi tao mang cac khoang cach lon nhat va gia tri tuong ung
        closest_distances = np.full(n_neighbors, 1e10)
        closest_values = np.zeros(n_neighbors)

        target = target_arr[i]
        if np.isnan(target):
            continue

        for j in range(1, window_size + 1):
            idx = i - j
            if idx < 0:
                break
            val = value_arr[idx]
            if np.isnan(val):
                continue

            distance = abs(target - val)

            # Tim vi tri co khoang cach lon nhat trong n_neighbors hien tai
            max_dist_idx = 0
            max_dist_val = closest_distances[0]
            for k in range(1, n_neighbors):
                if closest_distances[k] > max_dist_val:
                    max_dist_idx = k
                    max_dist_val = closest_distances[k]

            # Thay the neu distance nho hon khoang cach lon nhat
            if distance < max_dist_val:
                closest_distances[max_dist_idx] = distance
                closest_values[max_dist_idx] = val

        result[i] = closest_values.sum() / n_neighbors

    return result


# ---------------------------------------------------------------------------
# Core: KNN Prediction (classifier)
# ---------------------------------------------------------------------------

def _knn_prediction(
    price_arr: np.ndarray,
    c_arr: np.ndarray,
    o_arr: np.ndarray,
) -> np.ndarray:
    """
    KNN Classifier: voi moi nen, duyet 10 nen truoc,
    tim nen co distance nho nhat, dem Pos/Neg.

    Port tu PineScript:
        knn(price) =>
            for j = 1 to 10
                distance = sqrt((price[j] - price)^2)
                if distance < min_distance
                    min_distance := distance
                    nearest_index := j
                    Pos = c[nearest_index] < o[nearest_index]
                    Neg = c[nearest_index] > o[nearest_index]
                    if Pos => Pos_count += 1
                    if Neg => Neg_count += 1
            output = Pos_count > Neg_count ? 1 : -1
    """
    n = len(price_arr)
    result = np.full(n, np.nan)

    for i in range(10, n):
        pos_count = 0
        neg_count = 0
        min_distance = 1e10

        for j in range(1, 11):  # 1 to 10
            idx = i - j
            if idx < 0:
                break

            p_j = price_arr[idx]
            p_i = price_arr[i]
            if np.isnan(p_j) or np.isnan(p_i):
                continue

            distance = np.sqrt((p_j - p_i) ** 2)

            if distance < min_distance:
                min_distance = distance
                nearest_index = idx

                c_val = c_arr[nearest_index]
                o_val = o_arr[nearest_index]

                if not (np.isnan(c_val) or np.isnan(o_val)):
                    if c_val < o_val:  # Pos
                        pos_count += 1
                    if c_val > o_val:  # Neg
                        neg_count += 1

        result[i] = 1.0 if pos_count > neg_count else -1.0

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_knn_trend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    price_method: str = "hl2",
    target_method: str = "rma",
    ma_len: int = 5,
    target_ma_len: int = 5,
    n_neighbors: int = 3,
    smoothing_period: int = 50,
) -> dict[str, pd.Series]:
    """
    Tinh KNN Trend Navigator — chi bao xu huong dua tren K-Nearest Neighbors.

    Thuat toan:
        1) Tinh value_in = MA(price, ma_len) theo price_method
        2) Tinh target_in = MA(close, target_ma_len) theo target_method
        3) KNN MA: voi moi nen, tim n_neighbors gia tri value gan target nhat
           trong window_size = max(n_neighbors, 30) nen qua khu -> lay trung binh
        4) Smooth KNN MA bang WMA(5) -> knn_ma (duong xu huong chinh)
        5) KNN Avg = RMA(knn_ma_raw, smoothing_period) (duong cham)
        6) KNN Prediction: classifier dua tren 10 nen gan nhat -> +1/-1
        7) Tin hieu: crossover, crossunder, switch up/down

    Args:
        high            : pd.Series gia cao nhat moi nen
        low             : pd.Series gia thap nhat moi nen
        close           : pd.Series gia dong cua moi nen
        price_method    : Phuong phap tinh Price Value
                          "hl2" | "sma" | "ema" | "wma" | "hma"
        target_method   : Phuong phap tinh Target Value
                          "rma" | "sma" | "ema" | "wma" | "hma" | "atr"
        ma_len          : Chu ky MA cho Price Value (mac dinh 5)
        target_ma_len   : Chu ky MA cho Target Value (mac dinh 5)
        n_neighbors     : So neighbors KNN, cang cao cang muot (mac dinh 3)
        smoothing_period: Chu ky smooth cho KNN avg & prediction (mac dinh 50)

    Returns:
        dict[str, pd.Series] gom cac key:
            "knn_ma"          : Duong xu huong chinh (WMA-5 smoothed)
            "knn_avg"         : Duong trung binh cham (RMA-smoothing)
            "knn_prediction"  : +1 bullish, -1 bearish (WMA-3 smoothed)
            "knn_color"       : 1 Up, -1 Down, 0 Neutral
            "cross_over_avg"  : Bool — knn_ma cat len knn_avg
            "cross_under_avg" : Bool — knn_ma cat xuong knn_avg
            "switch_up"       : Bool — knn_ma bat dau tang
            "switch_down"     : Bool — knn_ma bat dau giam

    Vi du:
        result = calculate_knn_trend(df["high"], df["low"], df["close"])
        buy   = result["cross_over_avg"]
        sell  = result["cross_under_avg"]
        trend = result["knn_prediction"]
    """
    # Cast sang float, giu index
    high  = pd.Series(high.values,  index=high.index,  dtype=float)
    low   = pd.Series(low.values,   index=low.index,   dtype=float)
    close = pd.Series(close.values, index=close.index, dtype=float)
    idx   = close.index

    # ---- Step 1-2: Tinh value_in va target_in ----
    value_in  = _get_price_value(high, low, close, price_method, ma_len)
    target_in = _get_target_value(high, low, close, target_method, target_ma_len)

    # ---- Step 3: KNN Moving Average (meanOfKClosest) ----
    window_size = max(n_neighbors, 30)
    knn_ma_raw_arr = _mean_of_k_closest(
        value_arr=value_in.values,
        target_arr=target_in.values,
        n_neighbors=n_neighbors,
        window_size=window_size,
    )
    knn_ma_raw = pd.Series(knn_ma_raw_arr, index=idx, dtype=float)

    # ---- Step 4: Smooth KNN MA bang WMA(5) ----
    knn_ma = _wma(knn_ma_raw, 5)

    # ---- Step 5: KNN Average Line = RMA(knn_ma_raw, smoothing_period) ----
    knn_avg = _rma(knn_ma_raw, smoothing_period)

    # ---- Step 6: KNN Prediction ----
    # price = avg(knn_ma_raw, close)
    price = (knn_ma_raw + close) / 2.0

    # c = RMA(knn_ma_raw.shift(1), smoothing_period)
    # o = RMA(knn_ma_raw, smoothing_period)
    c_series = _rma(knn_ma_raw.shift(1), smoothing_period)
    o_series = _rma(knn_ma_raw, smoothing_period)

    knn_pred_raw_arr = _knn_prediction(
        price_arr=price.values,
        c_arr=c_series.values,
        o_arr=o_series.values,
    )
    knn_pred_raw = pd.Series(knn_pred_raw_arr, index=idx, dtype=float)

    # Smooth prediction bang WMA(3)
    knn_prediction = _wma(knn_pred_raw, 3)

    # ---- Step 7: Color & Signals ----
    # knn_color: 1 = Up (knn_ma > knn_ma_prev), -1 = Down, 0 = Neutral
    knn_ma_prev = knn_ma.shift(1)
    knn_color = pd.Series(0, index=idx, dtype=int)
    knn_color = knn_color.where(~(knn_ma > knn_ma_prev), 1)
    knn_color = knn_color.where(~(knn_ma < knn_ma_prev), -1)

    # Crossover / Crossunder
    cross_over_avg = (knn_ma > knn_avg) & (knn_ma.shift(1) <= knn_avg.shift(1))
    cross_under_avg = (knn_ma < knn_avg) & (knn_ma.shift(1) >= knn_avg.shift(1))

    # Switch Up: knn_ma[1] < knn_ma va knn_ma[1] <= knn_ma[2]
    # (nen truoc la day, bay gio bat dau tang)
    knn_ma_1 = knn_ma.shift(1)
    knn_ma_2 = knn_ma.shift(2)
    switch_up   = (knn_ma_1 < knn_ma) & (knn_ma_1 <= knn_ma_2)
    switch_down = (knn_ma_1 > knn_ma) & (knn_ma_1 >= knn_ma_2)

    # ---- Fill NaN bang gia tri mac dinh ----
    knn_ma         = knn_ma.fillna(0.0).rename("KNN_MA")
    knn_avg        = knn_avg.fillna(0.0).rename("KNN_AVG")
    knn_prediction = knn_prediction.fillna(0.0).rename("KNN_PRED")
    knn_color      = knn_color.fillna(0).rename("KNN_COLOR")
    cross_over_avg  = cross_over_avg.fillna(False).rename("CROSS_OVER_AVG")
    cross_under_avg = cross_under_avg.fillna(False).rename("CROSS_UNDER_AVG")
    switch_up       = switch_up.fillna(False).rename("SWITCH_UP")
    switch_down     = switch_down.fillna(False).rename("SWITCH_DOWN")

    return {
        "knn_ma":          knn_ma,
        "knn_avg":         knn_avg,
        "knn_prediction":  knn_prediction,
        "knn_color":       knn_color,
        "cross_over_avg":  cross_over_avg,
        "cross_under_avg": cross_under_avg,
        "switch_up":       switch_up,
        "switch_down":     switch_down,
    }
