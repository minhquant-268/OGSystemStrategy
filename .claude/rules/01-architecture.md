---
description: System architecture, data flow pipeline, and key source files. Load when understanding how components connect or modifying core orchestration.
alwaysApply: true
---

## System Purpose

Real-time trading signal generation. Subscribes to Redis for new candles → calculates indicators → applies strategies → filters via KNN → publishes signals to Redis for the downstream order executor (Module 5: OF_ctrader).

## Data Flow (Realtime)

```
Redis keyspace event  (Module 2 writes new candle)
  → keyspace_monitor.py   parse key, fetch candle bucket, build OHLCV DataFrame
  → strategy_engine.py    load config, dynamic-import strategy classes, filter df, run strategies
  → signal_filter.py      run KNN Trend; keep signal only when aligned with KNN prediction
  → redis_publisher.py    write OG hash, signal hash, publish pub/sub channel
  → Module 5 (OF_ctrader) subscribes and executes orders
```

## Layers

| Layer | Path | Responsibility |
|---|---|---|
| Entry points | `main.py`, `back_fill_og.py` | Realtime loop / historical backfill |
| Core | `src/core/` | Orchestration, event listening, publishing, cleanup |
| Strategies | `src/strategies/` | Signal logic (extend `BaseStrategy`) |
| Indicators | `src/indicators/` | Pure stateless math functions |
| Utils | `src/utils/` | Logging, DB connection (SQL Server), Redis helpers |
| Config | `config/` | JSON-driven strategy/indicator/output definitions |

## Key Files

- **`src/core/strategy_engine.py`** — Orchestrator. Loads `config/strategy_list.json`, dynamically imports strategy classes, filters DataFrames by (provider, symbol, timeframe), returns `List[StrategyResult]`.
- **`src/core/keyspace_monitor.py`** — Subscribes to `__keyspace@0__:candle:*`, builds OHLCV DataFrames, triggers the engine.
- **`src/core/redis_publisher.py`** — Writes OG hashes (every candle) and signal hashes (BUY/SELL only), publishes pub/sub channels, maintains list indexes.
- **`src/core/signal_filter.py`** — KNN Trend filter. Saves original signal to `strategy_signal` column; nulls entry/sl/tp when signal contradicts KNN prediction.
- **`src/core/cleanup_worker.py`** — Daemon thread (every 5 min) that trims OG/signal lists to 1000 items and deletes orphaned hashes.
- **`src/strategies/base_strategy.py`** — ABC with required `calculate_signals(df) -> DataFrame` method.
