---
description: KNN Trend Navigator algorithm internals, outputs, signal filter integration, tuning parameters, and usage in strategies. Load when working on KNN indicator, signal_filter, or adding KNN-based signal logic.
globs: src/indicators/KNN_trend.py,src/core/signal_filter.py,src/strategies/**/*.py
---

## Overview

Ported from PineScript **AI Trend Navigator** by Zeiierman.
- Implementation: `src/indicators/KNN_trend.py`
- Filter integration: `src/core/signal_filter.py`

The algorithm runs two independent KNN passes per candle to produce a trend line and a trend direction classifier.

---

## Pass 1 — KNN Moving Average (`knn_ma`)

For each candle `i`, scan the previous `window_size = max(n_neighbors, 30)` candles. Keep the `n_neighbors` candles whose `value_in` (smoothed price) is closest in absolute distance to the current `target_in` (reference price). Average those neighbors → `knn_ma_raw`.

```
value_in  = MA(price, ma_len)       # default: SMA((high+low)/2, 5)
target_in = MA(close, target_ma_len) # default: RMA(close, 5)

distance  = |target_in[i] - value_in[i-j]|   for j in 1..window_size
knn_ma_raw[i] = mean of the n_neighbors closest value_in values
```

Then smooth:
- `knn_ma  = WMA(knn_ma_raw, 5)` — fast trend line
- `knn_avg = RMA(knn_ma_raw, smoothing_period)` — slow reference line

---

## Pass 2 — KNN Prediction classifier (`knn_prediction`)

Build a pseudo-candle from the KNN MA:
```
price = (knn_ma_raw + close) / 2             # distance metric
c     = RMA(knn_ma_raw.shift(1), smoothing_period)  # pseudo-close (lagged)
o     = RMA(knn_ma_raw,          smoothing_period)  # pseudo-open
```

For each candle, scan the 10 previous candles. Each time a new minimum distance is found, inspect the pseudo-candle at that index:
- `c < o` → bullish → `Pos_count += 1`
- `c > o` → bearish → `Neg_count += 1`

Result: `+1` if `Pos > Neg`, else `-1`. Smoothed with `WMA(3)`.

---

## Outputs — `calculate_knn_trend()` return dict

| Key | Meaning |
|-----|---------|
| `knn_ma` | Fast trend line (WMA-5 smoothed KNN MA) |
| `knn_avg` | Slow reference line (RMA over `smoothing_period`) |
| `knn_prediction` | `> 0` bullish, `< 0` bearish (WMA-3 smoothed) |
| `knn_color` | `1` rising, `-1` falling, `0` neutral |
| `cross_over_avg` | `True` when `knn_ma` crosses above `knn_avg` (buy signal) |
| `cross_under_avg` | `True` when `knn_ma` crosses below `knn_avg` (sell signal) |
| `switch_up` | `True` when `knn_ma` reverses upward from a local low |
| `switch_down` | `True` when `knn_ma` reverses downward from a local high |

---

## Signal Filter Integration (`signal_filter.py`)

`apply_knn_filter(result, knn_config)` wraps any `StrategyResult` without modifying strategy code:

1. Copies strategy's `signal` → `strategy_signal` (kept in Redis for debugging).
2. Runs `calculate_knn_trend` on the result DataFrame.
3. Appends `KNN_MA`, `KNN_AVG`, `KNN_PRED`, `KNN_COLOR` columns to the DataFrame.
4. Alignment rule:
   - BUY passes only when `knn_prediction > 0`
   - SELL passes only when `knn_prediction < 0`
   - Misaligned → `signal = 0`, `entry/sl/tp/sl_distance/tp_distance = NaN`
5. On any exception, falls back to the original strategy signal (never silently drops).

---

## Tuning Parameters

| Parameter | Default | Effect of increasing |
|-----------|---------|----------------------|
| `n_neighbors` | 3 | Smoother `knn_ma`, less reactive to recent price |
| `smoothing_period` | 50 | Slower `knn_avg` and prediction; wider classification window |
| `ma_len` | 5 | Smoother `value_in` input fed to KNN pass 1 |
| `target_ma_len` | 5 | Smoother `target_in` reference for distance calculation |

Configure per-strategy in `config/strategy_list.json`:
```json
"knn_filter": { "enabled": true, "n_neighbors": 3, "smoothing_period": 50 }
```

---

## Usage in a Strategy

```python
from src.indicators.KNN_trend import calculate_knn_trend

knn = calculate_knn_trend(
    high=df["high"], low=df["low"], close=df["close"],
    n_neighbors=3, smoothing_period=50,
)

# Simple crossover signals
buy_signal  = knn["cross_over_avg"]
sell_signal = knn["cross_under_avg"]

# Strong signals: crossover confirmed by prediction
strong_buy  = (knn["knn_prediction"] > 0) & knn["cross_over_avg"]
strong_sell = (knn["knn_prediction"] < 0) & knn["cross_under_avg"]
```
