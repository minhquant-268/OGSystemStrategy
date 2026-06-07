---
description: Redis key naming conventions, hash schemas, and pub/sub channel patterns. Load when working on redis_publisher, keyspace_monitor, or any code that reads/writes Redis keys.
globs: src/core/**/*.py,src/utils/connection/redis_connect.py
---

## Key Patterns

| Key pattern | Type | Purpose |
|---|---|---|
| `candle:{provider}:{symbol}:{tf}:{datetime}` | Hash | Input candles from Module 2 (price feeder) |
| `OG:{strategy}:{provider}:{symbol}:{tf}:{datetime}` | Hash | All candles + all indicator columns |
| `OG:{strategy}:{provider}:{symbol}:{tf}` | List | Ordered index of datetimes for the OG hashes |
| `signal:{strategy}:{provider}:{symbol}:{tf}:{datetime}` | Hash | BUY/SELL candles only |
| `signal:{strategy}:{provider}:{symbol}:{tf}` | List | Ordered index of datetimes for signal hashes |
| `signals_channel:{strategy}:{provider}:{symbol}:{tf}` | Pub/Sub | JSON payload published to OF_ctrader |

## Field Notes

- OG hashes contain every candle regardless of signal, with all indicator values (SMA, MACD, ATR, KNN_*, etc.).
- Signal hashes are written only when `signal == 1` (BUY) or `signal == 2` (SELL).
- `strategy_signal` field in hashes holds the raw strategy signal before KNN filtering.
- Lists are capped at 1000 items by `cleanup_worker.py` (RPOP oldest, delete orphaned hashes).

## Keyspace Subscription

`keyspace_monitor.py` subscribes to:
```
__keyspace@0__:candle:*
```
Event type listened for: `hset` (new candle written as a hash).
