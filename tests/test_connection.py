"""
test_connection.py
==================
Test Module Connection:
  1. Ket noi SQL Server va lay du lieu nen
  2. Day du lieu tu DB len Redis de kiem tra tren Redis Desktop
  3. Ket noi Redis va verify cac operation

Flow chinh:
  DB (US30, tat ca provider) --> get_candles() --> Redis hash keys
  Key format: test:db_to_redis:{provider}:{symbol}:{timeframe}:{datetime}

Chay:
    python tests/test_connection.py              # Ghi data len Redis, GIU LAI de xem
    python tests/test_connection.py --clean      # Chay xong XOA sach test keys
    python tests/test_connection.py --timeframe m15  # Chi dinh timeframe (mac dinh: m10)

Du lieu tren Redis Desktop sau khi chay:
    DB0 -> test:db_to_redis:*  (Hash - moi key la 1 cay nen)
"""

import sys
import os
import json
import logging

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "buffer"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---- Path setup ----------------------------------------------------------
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# --------------------------------------------------------------------------

import pandas as pd

from src.utils.connection.redis_connect import (
    get_redis_client,
    close_redis_client,
    scan_keys,
    hset_hash,
    lpush_list,
)
from src.utils.connection.db_connect import (
    test_connection as db_test_connection,
    get_candles,
    engine,
)
from sqlalchemy import text

# ---- Logger ---------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_connection")

# ---- Parse CLI args --------------------------------------------------------
CLEAN_AFTER = "--clean" in sys.argv    # Xoa test keys sau khi chay

# Parse --timeframe
TIMEFRAME = "m10"
for arg in sys.argv:
    if arg.startswith("--timeframe="):
        TIMEFRAME = arg.split("=", 1)[1]
    elif arg == "--timeframe" and sys.argv.index(arg) + 1 < len(sys.argv):
        TIMEFRAME = sys.argv[sys.argv.index(arg) + 1]

# ---- Constants -------------------------------------------------------------
TEST_SYMBOL        = "US30"
TEST_LIMIT         = 10              # 10 nen gan nhat
PROVIDERS_TO_TRY   = ["CAPITALCOM", "BINANCE", "FXCM"]   # Thu lan luot
REDIS_PREFIX       = "test:db_to_redis"   # Prefix cho toan bo test key
SEP1 = "=" * 65
SEP2 = "-" * 65


# ==========================================================================
# Helper: Lay danh sach provider tu DB co du lieu US30
# ==========================================================================

def get_available_providers(symbol: str) -> list:
    """
    Lay danh sach provider tu bang dbo.assets co du lieu cho symbol nay.
    Khong dua tren hardcode, thay vao do query thang tu DB.
    """
    if engine is None:
        return []
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT DISTINCT provider FROM dbo.assets WHERE symbol = :symbol"),
                {"symbol": symbol}
            )
            providers = [row[0] for row in result.fetchall()]
        if providers:
            print(f"  [DB]  Tim thay {len(providers)} provider cho {symbol}: {providers}")
        else:
            print(f"  [DB]  Khong tim thay provider nao cho {symbol} trong dbo.assets")
        return providers
    except Exception as e:
        print(f"  [WARN] Khong the query providers tu DB: {e}")
        print(f"  [INFO] Su dung danh sach thu: {PROVIDERS_TO_TRY}")
        return PROVIDERS_TO_TRY


# ==========================================================================
# BLOCK 1 — SQL DB
# ==========================================================================

def test_db_connection():
    print("\n" + SEP1)
    print("TEST 1.1 - SQL Server Connection")
    print(SEP1)
    ok = db_test_connection()
    if ok:
        print("  [PASS] Ket noi SQL Server thanh cong")
    else:
        print("  [FAIL] Khong the ket noi SQL Server")
        print("  Check .env: DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, DB_DRIVER")
    return ok


def fetch_candles_all_providers(symbol: str, timeframe: str, limit: int):
    """
    Lay du lieu nen tu DB cho symbol, tat ca provider co du lieu.
    Tra ve dict: {provider: DataFrame}
    """
    print("\n" + SEP2)
    print(f"TEST 1.2 - get_candles cho tat ca provider")
    print(f"  Symbol    : {symbol}")
    print(f"  Timeframe : {timeframe}")
    print(f"  Limit     : {limit} nen gan nhat")
    print(SEP2)

    providers = get_available_providers(symbol)
    results = {}

    for provider in providers:
        print(f"\n  >> Query: symbol={symbol}, timeframe={timeframe}, provider={provider}")
        try:
            df = get_candles(
                symbol=symbol,
                timeframe=timeframe,
                provider=provider,
                limit=limit,
            )
            if df.empty:
                print(f"     [SKIP] Khong co du lieu cho {provider}/{symbol}/{timeframe}")
            else:
                print(f"     [OK]   {len(df)} nen | Tu: {df['date_time'].iloc[0]} -> Den: {df['date_time'].iloc[-1]}")
                print(df[["date_time", "open", "high", "low", "close", "volume"]].tail(3).to_string(index=False))
                results[provider] = df
        except Exception as e:
            print(f"     [ERR]  Loi khi query {provider}: {e}")

    if results:
        print(f"\n  [PASS] Lay duoc du lieu tu {len(results)} provider: {list(results.keys())}")
    else:
        print(f"\n  [FAIL] Khong lay duoc du lieu tu bat ky provider nao cho {symbol}/{timeframe}")
    return results


# ==========================================================================
# BLOCK 2 — Redis: Day du lieu DB len Redis
# ==========================================================================

def test_redis_connection():
    print("\n" + SEP1)
    print("TEST 2.1 - Redis Connection")
    print(SEP1)

    client = get_redis_client(db=0)
    if client is None:
        print("  [FAIL] Khong the ket noi Redis")
        print("  Check .env: REDIS_HOST, REDIS_PORT, REDIS_PASSWORD")
        return False, None

    info = client.info("server")
    print("  [PASS] Ket noi Redis thanh cong")
    print(f"  Host    : {client.connection_pool.connection_kwargs.get('host', 'N/A')}")
    print(f"  Port    : {client.connection_pool.connection_kwargs.get('port', 'N/A')}")
    print(f"  Version : {info.get('redis_version', 'N/A')}")
    return True, client


def push_candles_to_redis(client, candles_by_provider: dict, symbol: str, timeframe: str):
    """
    Day tung cay nen tu DB len Redis duoi dang Hash.

    Key format:
      Hash : test:db_to_redis:{provider}:{symbol}:{timeframe}:{datetime}
      List : test:db_to_redis:{provider}:{symbol}:{timeframe}   <-- index danh sach datetime

    Sau khi chay, Redis Desktop se hien thi cac key trong DB0.
    """
    print("\n" + SEP2)
    print("TEST 2.2 - Day du lieu DB -> Redis")
    print(f"  Key prefix: {REDIS_PREFIX}")
    print(SEP2)

    if not candles_by_provider:
        print("  [SKIP] Khong co du lieu DB de day len Redis")
        return []

    all_written_keys = []

    for provider, df in candles_by_provider.items():
        list_key    = f"{REDIS_PREFIX}:{provider}:{symbol}:{timeframe}"
        written_keys = []

        print(f"\n  Provider: {provider} | {len(df)} nen")
        print(f"  Hash key : {REDIS_PREFIX}:{provider}:{symbol}:{timeframe}:{{datetime}}")
        print(f"  List key : {list_key}")

        # Xoa list key cu truoc khi ghi moi (de khong bi trung lap)
        client.delete(list_key)

        for _, row in df.iterrows():
            dt_str  = str(row["date_time"])
            hash_key = f"{REDIS_PREFIX}:{provider}:{symbol}:{timeframe}:{dt_str}"

            payload = {
                "date_time"   : dt_str,
                "close_time"  : str(row["close_time"]),
                "provider"    : provider,
                "symbol"      : symbol,
                "timeframe"   : timeframe,
                "open"        : str(row["open"]),
                "high"        : str(row["high"]),
                "low"         : str(row["low"]),
                "close"       : str(row["close"]),
                "volume"      : str(row["volume"]),
                "_source"     : "test:db_to_redis",
                "_written_at" : pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            ok_hash = hset_hash(client, hash_key, payload)
            ok_list = lpush_list(client, list_key, dt_str)

            if ok_hash and ok_list:
                written_keys.append(hash_key)
            else:
                print(f"     [ERR] Ghi that bai: {hash_key}")

        print(f"  [PASS] Da ghi {len(written_keys)}/{len(df)} nen len Redis")
        all_written_keys.extend(written_keys)
        all_written_keys.append(list_key)

    # Verify: doc lai tu Redis
    print(f"\n  Verify - Scan tat ca key prefix {REDIS_PREFIX}:* ...")
    visible_keys = scan_keys(client, f"{REDIS_PREFIX}:*")
    print(f"  [CHECK] Tim thay {len(visible_keys)} key tren Redis DB0")
    for k in sorted(visible_keys):
        ktype = client.type(k)
        if ktype == "hash":
            nfields = client.hlen(k)
            print(f"    HASH  ({nfields:2d} fields) : {k}")
        elif ktype == "list":
            nitem = client.llen(k)
            print(f"    LIST  ({nitem:2d} items ) : {k}")
        else:
            print(f"    {ktype.upper():5s}           : {k}")

    return all_written_keys


def cleanup_test_keys(client, keys: list):
    """Xoa tat ca test keys - chi goi khi co --clean flag"""
    print("\n" + SEP2)
    print("TEST 2.3 - Cleanup test keys (--clean flag)")
    print(SEP2)

    pattern_keys = scan_keys(client, f"{REDIS_PREFIX}:*")
    if not pattern_keys:
        print("  [INFO] Khong co key nao de xoa")
        return

    deleted = client.delete(*pattern_keys)
    print(f"  [DONE] Da xoa {deleted} key co prefix: {REDIS_PREFIX}:*")


# ==========================================================================
# MAIN
# ==========================================================================

def main():
    print("\n" + SEP1)
    print("  MODULE CONNECTION - DB to Redis Test")
    print(f"  Symbol    : {TEST_SYMBOL}")
    print(f"  Timeframe : {TIMEFRAME}")
    print(f"  Limit     : {TEST_LIMIT} nen")
    print(f"  Mode      : {'--clean (xoa sau khi test)' if CLEAN_AFTER else 'GIU DATA tren Redis Desktop'}")
    print(SEP1)

    results = {}

    # ---- Block 1: SQL DB ---------------------
    results["1.1 DB Connection"] = test_db_connection()

    candles_by_provider = {}
    if results["1.1 DB Connection"]:
        candles_by_provider = fetch_candles_all_providers(
            symbol=TEST_SYMBOL,
            timeframe=TIMEFRAME,
            limit=TEST_LIMIT,
        )
        results["1.2 DB fetch US30 (all providers)"] = bool(candles_by_provider)
    else:
        results["1.2 DB fetch US30 (all providers)"] = None

    # ---- Block 2: Redis ----------------------
    redis_ok, client = test_redis_connection()
    results["2.1 Redis Connection"] = redis_ok

    pushed_keys = []
    if redis_ok and client:
        pushed_keys = push_candles_to_redis(
            client,
            candles_by_provider,
            symbol=TEST_SYMBOL,
            timeframe=TIMEFRAME,
        )
        results["2.2 DB -> Redis push"] = bool(pushed_keys)

        if CLEAN_AFTER:
            cleanup_test_keys(client, pushed_keys)
            results["2.3 Cleanup"] = True
        else:
            results["2.3 Cleanup"] = None   # SKIP

        close_redis_client()
    else:
        results["2.2 DB -> Redis push"] = None
        results["2.3 Cleanup"] = None

    # ---- Summary -----------------------------
    print("\n" + SEP1)
    print("  KET QUA")
    print(SEP1)
    passed = failed = skipped = 0
    for name, result in results.items():
        if result is True:
            status = "[PASS]"; passed += 1
        elif result is False:
            status = "[FAIL]"; failed += 1
        else:
            status = "[SKIP]"; skipped += 1
        print(f"  {status:8s} {name}")
    print(SEP2)
    print(f"  PASS: {passed} | FAIL: {failed} | SKIP: {skipped}")
    print(SEP1)

    if not CLEAN_AFTER and pushed_keys:
        hash_count = sum(1 for k in pushed_keys if f":{TIMEFRAME}:" in k and k.count(":") > 4)
        list_count = sum(1 for k in pushed_keys if k.count(":") == 4)
        print(f"\n  Du lieu dang co tren Redis Desktop (DB0):")
        print(f"    Hash keys : {hash_count}  (moi key = 1 cay nen US30)")
        print(f"    List keys : {list_count}  (index danh sach datetime)")
        print(f"    Pattern   : {REDIS_PREFIX}:*")
        print(f"\n  --> Refresh Redis Desktop va mo DB0 de xem!")
        print(f"  --> Chay voi --clean de don dep: python tests/test_connection.py --clean")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
