"""Debug: check raw Redis data types from get_candle_bucket."""
import sys, os
sys.path.insert(0, os.getcwd())
from src.utils.connection.redis_connect import get_redis_client

client = get_redis_client()

# Check if decode_responses is enabled
print(f"Redis client type: {type(client)}")
print(f"Connection pool kwargs: {client.connection_pool.connection_kwargs}")

# Direct hgetall test
keys = []
cursor = 0
while True:
    cursor, batch = client.scan(cursor=cursor, match="candle:CAPITALCOM:BTCUSD:5:*", count=10)
    keys.extend(batch)
    if cursor == 0 or len(keys) >= 3:
        break

if keys:
    key = keys[0]
    print(f"\nKey type: {type(key)}, value: {key}")
    raw = client.hgetall(key)
    for k, v in list(raw.items())[:4]:
        print(f"  field type={type(k)}, value_type={type(v)}: {k} = {v}")
