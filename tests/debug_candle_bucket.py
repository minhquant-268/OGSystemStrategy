"""Debug: verify get_candle_bucket reads the 1008 candle keys."""
import sys, os
sys.path.insert(0, os.getcwd())

from src.utils.connection.redis_connect import get_redis_client, get_candle_bucket, scan_keys

client = get_redis_client()
if not client:
    print("Cannot connect to Redis")
    sys.exit(1)

# 1. Raw SCAN check
all_keys = scan_keys(client, "candle:CAPITALCOM:BTCUSD:5:*")
print(f"[1] Raw SCAN 'candle:CAPITALCOM:BTCUSD:5:*': {len(all_keys)} keys")

# Same but with key_type="hash"
hash_keys = scan_keys(client, "candle:CAPITALCOM:BTCUSD:5:*", key_type="hash")
print(f"[2] SCAN with key_type=hash: {len(hash_keys)} keys")

# Check types of first few keys
if all_keys:
    for k in all_keys[:3]:
        key_str = k.decode() if isinstance(k, bytes) else k
        ktype = client.type(key_str)
        ktype_str = ktype.decode() if isinstance(ktype, bytes) else ktype
        print(f"    key={key_str}, type={ktype_str}")

# 3. Test get_candle_bucket
records = get_candle_bucket(client, "CAPITALCOM", "BTCUSD", "5")
print(f"\n[3] get_candle_bucket: {len(records)} records")

if records:
    r = records[0]
    print(f"    Sample: open={r.get('open')}, close={r.get('close')}, dt={r.get('date_time')}")
    
    # Test building DF
    import pandas as pd
    df = pd.DataFrame(records)
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    nan_rows = df[["open","high","low","close"]].isna().any(axis=1).sum()
    print(f"    DF shape: {df.shape}, NaN OHLC rows: {nan_rows}")

# 4. Check list key type (might be blocking hash scan)
list_key = "candle:CAPITALCOM:BTCUSD:5"
list_type = client.type(list_key)
list_type_str = list_type.decode() if isinstance(list_type, bytes) else list_type
list_len = client.llen(list_key) if list_type_str == "list" else "N/A"
print(f"\n[4] List key '{list_key}': type={list_type_str}, len={list_len}")

print("\nDone.")
