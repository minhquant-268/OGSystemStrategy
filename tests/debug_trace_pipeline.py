"""Simulate exactly what handle_candle_event does — trace the full pipeline."""
import sys, os
sys.path.insert(0, os.getcwd())

from src.utils.connection.redis_connect import get_redis_client, get_candle_bucket
from src.core.strategy_engine import StrategyEngine
from src.core.keyspace_monitor import _build_df_from_bucket

client = get_redis_client()

# Simulate: candle event for CAPITALCOM:BTCUSD:5
provider, symbol, timeframe = "CAPITALCOM", "BTCUSD", "5"

# Step 1: get_candle_bucket
records = get_candle_bucket(client, provider, symbol, timeframe)
print(f"[1] get_candle_bucket: {len(records)} records")

# Step 2: _build_df_from_bucket
df = _build_df_from_bucket(records)
print(f"[2] _build_df_from_bucket: {df.shape}")

# Step 3: Add metadata (like handle_candle_event does)
df["provider"] = provider
df["symbol"] = symbol
df["timeframe"] = timeframe
print(f"[3] After metadata: {df.shape}")
print(f"    Columns: {list(df.columns)}")
print(f"    provider unique: {df['provider'].unique()}")
print(f"    symbol unique: {df['symbol'].unique()}")
print(f"    timeframe unique: {df['timeframe'].unique()}")

# Step 4: Run engine
config_path = os.path.join(os.getcwd(), "config", "strategy_list.json")
engine = StrategyEngine(config_path=config_path)
print(f"\n[4] StrategyEngine configs:")
for cfg in engine._configs:
    print(f"    name={cfg.name}, enabled={cfg.enabled}, symbols={cfg.symbols}, timeframes={cfg.timeframes}")

# Step 5: Test _filter_df manually
for cfg in engine._configs:
    if not cfg.enabled:
        continue
    sym_list = engine._resolve_symbol_list(cfg, df)
    print(f"\n[5] Strategy '{cfg.name}' resolve_symbol_list:")
    for sc in sym_list:
        print(f"    {sc}")
        df_filtered = engine._filter_df(df, sc["provider"], sc["symbol"], sc["timeframe"])
        print(f"    -> filtered: {len(df_filtered)} rows")

# Step 6: Actually run engine
print(f"\n[6] engine.run()...")
results = engine.run(df.copy())
print(f"    Results: {len(results)}")
for r in results:
    print(f"    - {r.strategy_name}: {r.provider}:{r.symbol}:{r.timeframe} | {len(r.df_result)} rows")
    # Check if signal column exists and has values
    if "signal" in r.df_result.columns:
        sig_counts = r.df_result["signal"].value_counts()
        print(f"      signals: {dict(sig_counts)}")
    if "SMA" in r.df_result.columns:
        sma_valid = r.df_result["SMA"].notna().sum()
        print(f"      SMA valid: {sma_valid}")
    if "MACD" in r.df_result.columns:
        macd_valid = r.df_result["MACD"].notna().sum()
        print(f"      MACD valid: {macd_valid}")

print("\nDone.")
