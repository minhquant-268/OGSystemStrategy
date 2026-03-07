"""
test_connection.py
==================
Test thủ công (manual test) cho Module Connection:
  - src/utils/connection/redis_connect.py
  - src/utils/connection/db_connect.py

Chạy:
    cd system_strategy_revise
    python tests/test_connection.py

Yêu cầu:
    - File .env đã điền đúng thông tin DB và Redis
    - Máy chủ DB và Redis đang chạy và có thể truy cập

Kết quả mong đợi khi PASS:
    [DB]    ✅ Kết nối SQL Server thành công
    [DB]    ✅ Query dữ liệu nến thành công — X rows
    [Redis] ✅ Kết nối Redis thành công
    [Redis] ✅ Đọc candle bucket thành công — X nến
    [Redis] ✅ Ghi hash key thành công
    [Redis] ✅ Publish channel thành công
    [Redis] ✅ Scan keys thành công
    [Redis] ✅ Cleanup test keys thành công
"""

import sys
import os
import logging

# ─── Path setup ───────────────────────────────────────────────
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
# ──────────────────────────────────────────────────────────────

import pandas as pd

from src.utils.connection.redis_connect import (
    create_redis_client,
    get_redis_client,
    close_redis_client,
    scan_keys,
    get_candle_bucket,
    hset_hash,
    lpush_list,
    publish_channel,
    enable_keyspace_notifications,
)
from src.utils.connection.db_connect import (
    test_connection as db_test_connection,
    get_candles,
)

# ─── Logger setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_connection")

# ─── Test config (chỉnh theo môi trường thực tế) ────────────
TEST_PROVIDER  = "CAPITALCOM"
TEST_SYMBOL    = "BTCUSD"
TEST_TIMEFRAME = "m10"          # Phải trùng với tên bảng tvc.m10 trong DB
TEST_LIMIT     = 50             # Lấy thử 50 nến để test nhanh
TEST_REDIS_KEY = "test:connection_module:temp_key"  # Key tạm để test, sẽ bị xóa sau


# ══════════════════════════════════════════════════════════════
# TEST BLOCK 1 — SQL Database Connection
# ══════════════════════════════════════════════════════════════

def test_db_connection():
    """Test 1.1 — Kết nối cơ bản tới SQL Server"""
    print("\n" + "═" * 60)
    print("TEST 1.1 — SQL Server Connection")
    print("═" * 60)

    result = db_test_connection()
    if result:
        print("  ✅ PASS — Kết nối SQL Server thành công")
    else:
        print("  ❌ FAIL — Không thể kết nối SQL Server")
        print("  ⚠️  Kiểm tra lại .env: DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, DB_DRIVER")
    return result


def test_db_get_candles():
    """Test 1.2 — Query dữ liệu nến lịch sử từ DB"""
    print("\n" + "─" * 60)
    print(f"TEST 1.2 — get_candles({TEST_SYMBOL}, {TEST_TIMEFRAME}, {TEST_PROVIDER}, limit={TEST_LIMIT})")
    print("─" * 60)

    df = get_candles(
        symbol=TEST_SYMBOL,
        timeframe=TEST_TIMEFRAME,
        provider=TEST_PROVIDER,
        limit=TEST_LIMIT,
    )

    if df.empty:
        print("  ❌ FAIL — DataFrame trống, không có dữ liệu")
        print(f"  ⚠️  Kiểm tra: bảng tvc.{TEST_TIMEFRAME} có dữ liệu cho {TEST_SYMBOL} ({TEST_PROVIDER})?")
        return False

    # Kiểm tra schema
    expected_cols = ["date_time", "close_time", "provider", "symbol", "timeframe",
                     "open", "high", "low", "close", "volume"]
    missing_cols  = [c for c in expected_cols if c not in df.columns]
    if missing_cols:
        print(f"  ❌ FAIL — Thiếu cột: {missing_cols}")
        return False

    print(f"  ✅ PASS — Query OK, nhận được {len(df)} nến")
    print(f"  📋 Schema: {list(df.columns)}")
    print(f"  📅 Từ:  {df['date_time'].iloc[0]}")
    print(f"  📅 Đến: {df['date_time'].iloc[-1]}")
    print(f"  📊 Tail 3 nến gần nhất:")
    print(df.tail(3).to_string(index=False))
    return True


# ══════════════════════════════════════════════════════════════
# TEST BLOCK 2 — Redis Connection
# ══════════════════════════════════════════════════════════════

def test_redis_connection():
    """Test 2.1 — Kết nối cơ bản tới Redis"""
    print("\n" + "═" * 60)
    print("TEST 2.1 — Redis Connection")
    print("═" * 60)

    client = get_redis_client(db=0)
    if client is None:
        print("  ❌ FAIL — Không thể kết nối Redis")
        print("  ⚠️  Kiểm tra lại .env: REDIS_HOST, REDIS_PORT, REDIS_PASSWORD")
        return False, None

    info = client.info("server")
    print(f"  ✅ PASS — Kết nối Redis thành công")
    print(f"  📌 Redis version: {info.get('redis_version', 'N/A')}")
    print(f"  📌 Mode: {info.get('redis_mode', 'standalone')}")
    return True, client


def test_redis_hset(client):
    """Test 2.2 — Ghi và đọc Hash key"""
    print("\n" + "─" * 60)
    print("TEST 2.2 — hset_hash (ghi hash key tạm)")
    print("─" * 60)

    test_payload = {
        "date_time": "2026-03-07 22:00:00",
        "symbol":    TEST_SYMBOL,
        "provider":  TEST_PROVIDER,
        "timeframe": TEST_TIMEFRAME,
        "signal":    "1",
        "entry":     "50000.5",
        "sl":        "49500.0",
        "tp":        "51000.0",
        "sl_distance": "500.5",
        "tp_distance": "999.5",
    }

    ok = hset_hash(client, TEST_REDIS_KEY, test_payload)
    if not ok:
        print("  ❌ FAIL — hset_hash thất bại")
        return False

    # Đọc lại để verify
    read_back = client.hgetall(TEST_REDIS_KEY)
    if not read_back:
        print("  ❌ FAIL — Không đọc được key vừa ghi")
        return False

    print(f"  ✅ PASS — Ghi và đọc lại Hash OK")
    print(f"  📋 Key: {TEST_REDIS_KEY}")
    for k, v in read_back.items():
        print(f"      {k}: {v}")
    return True


def test_redis_scan(client):
    """Test 2.3 — Scan keys theo pattern"""
    print("\n" + "─" * 60)
    print("TEST 2.3 — scan_keys (tìm candle bucket trên Redis)")
    print("─" * 60)

    pattern = f"candle:{TEST_PROVIDER}:{TEST_SYMBOL}:*"
    keys    = scan_keys(client, pattern)

    if not keys:
        print(f"  ⚠️  Không tìm thấy key nào — pattern={pattern}")
        print(f"  ℹ️  Module 2 (Data Feeder) có thể chưa đẩy nến lên Redis")
        return True   # Cho pass vì đây là môi trường test, không nhất thiết có data

    print(f"  ✅ PASS — Scan tìm thấy {len(keys)} key")
    print(f"  🗝️  Ví dụ 3 key đầu: {keys[:3]}")
    return True


def test_redis_candle_bucket(client):
    """Test 2.4 — get_candle_bucket đọc bucket nến"""
    print("\n" + "─" * 60)
    print(f"TEST 2.4 — get_candle_bucket({TEST_PROVIDER}, {TEST_SYMBOL}, {TEST_TIMEFRAME})")
    print("─" * 60)

    records = get_candle_bucket(client, TEST_PROVIDER, TEST_SYMBOL, TEST_TIMEFRAME)

    if not records:
        print(f"  ⚠️  Không có nến trong bucket — có thể Data Feeder chưa chạy")
        print(f"  ℹ️  Skip test này nếu môi trường test chưa có dữ liệu realtime")
        return True   # Cho pass vì optional

    print(f"  ✅ PASS — Đọc được {len(records)} nến từ bucket")
    sample = records[-1]
    print(f"  📊 Ví dụ 1 nến (keys): {list(sample.keys())}")
    return True


def test_redis_publish(client):
    """Test 2.5 — Publish lên pub/sub channel"""
    print("\n" + "─" * 60)
    print("TEST 2.5 — publish_channel")
    print("─" * 60)

    import json
    channel = f"signals_channel:test:{TEST_PROVIDER}:{TEST_SYMBOL}:{TEST_TIMEFRAME}"
    message = json.dumps({"test": True, "symbol": TEST_SYMBOL, "signal": 1})

    ok = publish_channel(client, channel, message)
    if ok:
        print(f"  ✅ PASS — Publish thành công")
        print(f"  📡 Channel: {channel}")
    else:
        print(f"  ❌ FAIL — Publish thất bại")
    return ok


def test_redis_cleanup(client):
    """Test 2.6 — Dọn dẹp test key"""
    print("\n" + "─" * 60)
    print("TEST 2.6 — Cleanup test keys")
    print("─" * 60)

    deleted = client.delete(TEST_REDIS_KEY)
    if deleted:
        print(f"  ✅ PASS — Đã xóa test key: {TEST_REDIS_KEY}")
    else:
        print(f"  ⚠️  Key không tìm thấy để xóa (có thể đã xóa rồi)")
    return True


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("\n" + "█" * 60)
    print("  MODULE CONNECTION — Manual Test Runner")
    print("  system_strategy_revise / tests/test_connection.py")
    print("█" * 60)

    results = {}

    # ── Block 1: SQL DB ─────────────────────
    results["1.1 DB Connection"]   = test_db_connection()
    if results["1.1 DB Connection"]:
        results["1.2 DB get_candles"] = test_db_get_candles()
    else:
        results["1.2 DB get_candles"] = "SKIP (DB không kết nối được)"

    # ── Block 2: Redis ──────────────────────
    redis_ok, client = test_redis_connection()
    results["2.1 Redis Connection"] = redis_ok

    if redis_ok and client:
        results["2.2 Redis hset"]    = test_redis_hset(client)
        results["2.3 Redis scan"]    = test_redis_scan(client)
        results["2.4 Redis bucket"]  = test_redis_candle_bucket(client)
        results["2.5 Redis publish"] = test_redis_publish(client)
        results["2.6 Redis cleanup"] = test_redis_cleanup(client)
        close_redis_client()
    else:
        for k in ["2.2 Redis hset", "2.3 Redis scan", "2.4 Redis bucket",
                  "2.5 Redis publish", "2.6 Redis cleanup"]:
            results[k] = "SKIP (Redis không kết nối được)"

    # ── Summary ─────────────────────────────
    print("\n" + "═" * 60)
    print("  KẾT QUẢ TỔNG HỢP")
    print("═" * 60)
    passed = skipped = failed = 0
    for name, result in results.items():
        if result is True:
            status = "✅ PASS"
            passed += 1
        elif result is False:
            status = "❌ FAIL"
            failed += 1
        else:
            status = f"⏭️  SKIP"
            skipped += 1
        print(f"  {status}  {name}")
    print("─" * 60)
    print(f"  PASS: {passed} | FAIL: {failed} | SKIP: {skipped}")
    print("═" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
