---
description: How to create a new trading strategy. Load when adding, editing, or reviewing strategy files in src/strategies/.
globs: src/strategies/**/*.py
---

## Adding a New Strategy

1. Create `src/strategies/strategy_<name>.py` extending `BaseStrategy`.
2. Implement `calculate_signals(df: pd.DataFrame) -> pd.DataFrame` — must return columns: `signal`, `entry`, `sl`, `tp`, plus any indicator columns.
3. Add an entry to `config/strategy_list.json` with `"enabled": true`.
4. Add tests in `tests/test_strategies.py`.

No engine code changes needed — the engine dynamically imports from the class path in config.

## Signal column contract

| Value | Meaning |
|-------|---------|
| `0` | HOLD (no signal) |
| `1` | BUY |
| `2` | SELL |

`entry`, `sl`, `tp` must be numeric (price levels). Set to `NaN` when `signal == 0`.

## BaseStrategy contract

```python
from src.strategies.base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # df has columns: open, high, low, close, volume, datetime
        # must return df with at minimum: signal, entry, sl, tp
        ...
        return df
```

## strategy_list.json entry

```json
{
  "name": "my_strategy",
  "enabled": true,
  "class": "src.strategies.strategy_my_strategy.MyStrategy",
  "symbols": ["BTCUSD"],       // or "all"
  "timeframes": ["5", "15"],   // or "all"
  "knn_filter": { "enabled": true, "n_neighbors": 3, "smoothing_period": 50 }
}
```
