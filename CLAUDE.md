# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time trading signal generation system. Listens for new candles via Redis keyspace notifications, calculates technical indicators, applies trading strategies, filters signals with KNN Trend analysis, and publishes results to Redis for a downstream order execution module.

## Commands

**Install dependencies:**
```bash
pip install -r docs/requirements.txt
```

**Run realtime mode:**
```bash
python main.py
```

**Run backfill (populate Redis from SQL Server history):**
```bash
python back_fill_og.py                          # all providers, 1000 candles each
python back_fill_og.py --limit 500              # custom candle limit
python back_fill_og.py --provider CAPITALCOM    # single provider
```

**Run tests:**
```bash
pytest tests/                                   # all tests
pytest tests/test_strategies.py -v              # specific file
pytest tests/test_strategies.py::TestComboATR -v  # specific class
pytest --cov=src tests/                         # with coverage
```

**Type checking:**
```bash
pyright                                         # uses pyrightconfig.json (Python 3.10)
```

## Architecture

### Data Flow (Realtime)

```
Redis keyspace event (new candle written by Module 2: price feeder)
  → keyspace_monitor.py      parse key, fetch candle bucket, build DataFrame
  → strategy_engine.py       load config, dynamic-import strategy classes, filter df, run strategies
  → signal_filter.py         run KNN Trend; keep signal only when aligned with KNN prediction
  → redis_publisher.py       write OG hash, signal hash, publish pub/sub channel
  → Module 5 (OF_ctrader)    subscribes and executes orders
```

### Layers

| Layer | Path | Responsibility |
|---|---|---|
| Entry points | `main.py`, `back_fill_og.py` | Realtime loop / historical backfill |
| Core | `src/core/` | Orchestration, event listening, publishing, cleanup |
| Strategies | `src/strategies/` | Signal logic (extend `BaseStrategy`) |
| Indicators | `src/indicators/` | Pure stateless math functions |
| Utils | `src/utils/` | Logging, DB connection (SQL Server), Redis helpers |
| Config | `config/` | JSON-driven strategy/indicator/output definitions |

### Key Files

- **`src/core/strategy_engine.py`** — Orchestrator. Loads `config/strategy_list.json`, dynamically imports strategy classes, filters DataFrames by (provider, symbol, timeframe), returns `List[StrategyResult]`.
- **`src/core/keyspace_monitor.py`** — Subscribes to `__keyspace@0__:candle:*`, builds OHLCV DataFrames, triggers the engine.
- **`src/core/redis_publisher.py`** — Writes OG hashes (every candle) and signal hashes (BUY/SELL only), publishes pub/sub channels, maintains list indexes.
- **`src/core/signal_filter.py`** — KNN Trend filter. Saves original signal to `strategy_signal` column; nulls entry/sl/tp when strategy signal contradicts KNN prediction.
- **`src/core/cleanup_worker.py`** — Daemon thread (every 5 min) that trims OG/signal lists to 1000 items and deletes orphaned hashes.
- **`src/strategies/base_strategy.py`** — ABC with required `calculate_signals(df) -> DataFrame` method.

### Redis Key Schema

| Key pattern | Type | Purpose |
|---|---|---|
| `candle:{provider}:{symbol}:{tf}:{datetime}` | Hash | Input from price feeder |
| `OG:{strategy}:{provider}:{symbol}:{tf}:{datetime}` | Hash | All candles + indicators |
| `OG:{strategy}:{provider}:{symbol}:{tf}` | List | Index of datetimes |
| `signal:{strategy}:{provider}:{symbol}:{tf}:{datetime}` | Hash | BUY/SELL candles only |
| `signals_channel:{strategy}:{provider}:{symbol}:{tf}` | Pub/Sub | JSON payload to OF_ctrader |

### Configuration (`config/strategy_list.json`)

```json
{
  "name": "comboATR",
  "enabled": true,
  "class": "src.strategies.strategy_comboATR.ComboATRStrategy",
  "symbols": ["BTCUSD"],        // or "all"
  "timeframes": ["5", "15"],    // or "all"
  "knn_filter": { "enabled": true, "n_neighbors": 3, "smoothing_period": 50 }
}
```

Add a new strategy by adding an entry here — no engine code changes needed.

### Environment Variables (`.env`, not in git)

```
DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, DB_DRIVER   # SQL Server (ODBC Driver 17)
REDIS_HOST, REDIS_PORT, REDIS_PASSWORD                 # Redis
```

## KNN Trend Navigator

Ported from PineScript **AI Trend Navigator** by Zeiierman. Implementation: `src/indicators/KNN_trend.py`. Integrated as a post-strategy signal filter via `src/core/signal_filter.py`.

### How it works

The algorithm runs in two independent KNN passes on each candle:

**Pass 1 — KNN Moving Average (`knn_ma`)**

For each candle `i`, scan the previous `window_size = max(n_neighbors, 30)` candles. Keep the `n_neighbors` candles whose `value_in` (smoothed price) is closest in absolute distance to the current `target_in` (reference price). Average those `n_neighbors` values → `knn_ma_raw`. Then:
- `knn_ma  = WMA(knn_ma_raw, 5)` — fast trend line
- `knn_avg = RMA(knn_ma_raw, smoothing_period)` — slow reference line

**Pass 2 — KNN Prediction classifier (`knn_prediction`)**

For each candle, build a pseudo-candle from the KNN MA:
```
price = (knn_ma_raw + close) / 2        # distance metric
c = RMA(knn_ma_raw.shift(1), smoothing_period)   # pseudo-close (lagged)
o = RMA(knn_ma_raw,           smoothing_period)   # pseudo-open
```
Scan the 10 previous candles for the one with the smallest `|price[j] - price[i]|`. Each time a new minimum is found, inspect that candle's pseudo-candle: `c < o` → bullish (Pos+1), `c > o` → bearish (Neg+1). Result: `+1` if `Pos > Neg`, else `-1`. Smoothed with `WMA(3)`.

### Outputs (`calculate_knn_trend` return dict)

| Key | Meaning |
|-----|---------|
| `knn_ma` | Fast trend line (WMA-5 smoothed KNN MA) |
| `knn_avg` | Slow reference line (RMA over smoothing_period) |
| `knn_prediction` | `> 0` bullish, `< 0` bearish (WMA-3 smoothed) |
| `knn_color` | `1` rising, `-1` falling, `0` neutral |
| `cross_over_avg` | `True` when `knn_ma` crosses above `knn_avg` (buy signal) |
| `cross_under_avg` | `True` when `knn_ma` crosses below `knn_avg` (sell signal) |
| `switch_up` | `True` when `knn_ma` reverses upward from a local low |
| `switch_down` | `True` when `knn_ma` reverses downward from a local high |

### Signal filter integration (`signal_filter.py`)

`apply_knn_filter(result, knn_config)` wraps any `StrategyResult` without touching strategy code:

1. Copies strategy's `signal` column → `strategy_signal` (preserved in Redis for debugging).
2. Runs `calculate_knn_trend` on the result DataFrame.
3. Appends `KNN_MA`, `KNN_AVG`, `KNN_PRED`, `KNN_COLOR` columns to the DataFrame.
4. Alignment rule: BUY passes only when `knn_prediction > 0`; SELL passes only when `knn_prediction < 0`. Misaligned signals → `signal = 0` (HOLD), `entry/sl/tp/sl_distance/tp_distance` set to `NaN`.
5. On any exception, falls back to the original strategy signal (never silently drops).

KNN filter is **per-strategy** and toggled in `config/strategy_list.json`:
```json
"knn_filter": { "enabled": true, "n_neighbors": 3, "smoothing_period": 50 }
```

### Tuning parameters

| Parameter | Default | Effect of increasing |
|-----------|---------|----------------------|
| `n_neighbors` | 3 | Smoother `knn_ma`, less reactive |
| `smoothing_period` | 50 | Slower `knn_avg` and prediction; wider filter window |
| `ma_len` | 5 | Smoother `value_in` input to KNN |
| `target_ma_len` | 5 | Smoother `target_in` reference |

### Using KNN in a strategy directly

```python
from src.indicators.KNN_trend import calculate_knn_trend

result = calculate_knn_trend(
    high=df["high"], low=df["low"], close=df["close"],
    n_neighbors=3, smoothing_period=50,
)

# Combine with strategy logic
strong_buy  = (knn_result["knn_prediction"] > 0) & result["cross_over_avg"]
strong_sell = (knn_result["knn_prediction"] < 0) & result["cross_under_avg"]
```

## Adding a New Strategy

1. Create `src/strategies/strategy_<name>.py` extending `BaseStrategy`.
2. Implement `calculate_signals(df: pd.DataFrame) -> pd.DataFrame` — must return columns: `signal`, `entry`, `sl`, `tp`, plus any indicator columns.
3. Add an entry to `config/strategy_list.json` with `"enabled": true`.
4. Add tests in `tests/test_strategies.py`.

## Testing Notes

- Tests use synthetic DataFrames; no live DB or Redis required for unit tests.
- `test_connection.py` requires a live SQL Server and Redis — skip in offline environments.
- Signal filter tests live in `tests/test_signal_filter.py` (15+ cases covering alignment, fallback, and edge cases).
