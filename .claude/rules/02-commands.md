---
description: Commands for installing dependencies, running the app, backfilling data, running tests, and type checking.
alwaysApply: true
---

## Install

```bash
pip install -r docs/requirements.txt
```

## Run

```bash
# Realtime mode (subscribes to Redis keyspace events)
python main.py

# Backfill Redis from SQL Server history
python back_fill_og.py                          # all providers, 1000 candles each
python back_fill_og.py --limit 500              # custom candle limit
python back_fill_og.py --provider CAPITALCOM    # single provider
```

## Test

```bash
pytest tests/                                       # all tests
pytest tests/test_strategies.py -v                  # specific file
pytest tests/test_strategies.py::TestComboATR -v    # specific class
pytest --cov=src tests/                             # with coverage
```

## Type Check

```bash
pyright    # configured via pyrightconfig.json, Python 3.10
```
