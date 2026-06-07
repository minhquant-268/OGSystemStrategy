---
description: Configuration file formats (strategy_list.json) and required environment variables. Load when editing config files or setting up the environment.
globs: config/**/*.json
---

## strategy_list.json

Each object in the array configures one strategy:

```json
{
  "name": "comboATR",
  "enabled": true,
  "class": "src.strategies.strategy_comboATR.ComboATRStrategy",
  "symbols": ["BTCUSD"],       // or "all" to match every symbol
  "timeframes": ["5", "15"],   // or "all" to match every timeframe
  "knn_filter": {
    "enabled": true,
    "n_neighbors": 3,
    "smoothing_period": 50
  }
}
```

- `class` is a dotted Python import path — the engine imports it dynamically at runtime.
- `symbols`/`timeframes` with `"all"` are resolved against what the price feeder actually publishes.
- `knn_filter` is optional; omitting it uses `DEFAULT_KNN_CONFIG` in `signal_filter.py`.

## Environment Variables (`.env`, not in git)

```
# SQL Server (ODBC Driver 17 for SQL Server)
DB_SERVER=
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_DRIVER=ODBC Driver 17 for SQL Server

# Redis
REDIS_HOST=
REDIS_PORT=6379
REDIS_PASSWORD=
```
