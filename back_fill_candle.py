"""
back_fill_candle.py — Backfill candle HASH keys lên Redis
=========================================================
Tương tự back_fill_candle.py của system_strategy_NP, nhưng sử dụng
hạ tầng của system_strategy_revise (db_connect, redis_connect, strategy_list.json).

Flow:
    1. Đọc strategy_list.json → lấy danh sách (symbol, timeframe) cần backfill
    2. Với mỗi (provider, symbol, timeframe): query 995 nến từ SQL Server
    3. So sánh với Redis → tìm nến thiếu
    4. Ghi nến thiếu vào Redis dạng HASH: candle:{provider}:{symbol}:{tf}:{dt}
    5. Rebuild list key và trim giữ tối đa 995 nến

Redis schema:
    - Hash:  candle:{provider}:{symbol}:{timeframe}:{YYYY-MM-DD HH:MM:SS}
    - List:  candle:{provider}:{symbol}:{timeframe}  (DESC, newest first)

Chạy:
    python back_fill_candle.py
    python back_fill_candle.py --limit 500
    python back_fill_candle.py --provider CAPITALCOM
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime, timezone
from typing import List, Dict, Set

import pandas as pd

# Thêm project root vào sys.path
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from src.utils.logger import setup_logger, get_logger
from src.utils.connection.db_connect import get_candles, engine as db_engine
from src.utils.connection.redis_connect import create_redis_client
from sqlalchemy import text as sql_text

logger = get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_LIMIT    = 995
CONFIG_PATH      = os.path.join(project_root, "config", "strategy_list.json")


# ─────────────────────────────────────────────────────────────────────────────
# Timeframe conversion
# ─────────────────────────────────────────────────────────────────────────────

def _convert_timeframe_for_db(tf: str) -> str:
    """
    Convert timeframe từ config format sang DB format.
    Config: "5", "10", "15", "60", "240"
    DB:     "m5", "m10", "m15", "h1", "h4"
    """
    try:
        minutes = int(tf)
    except (ValueError, TypeError):
        return tf  # Nếu đã có prefix → giữ nguyên

    if minutes < 60:
        return f"m{minutes}"
    elif minutes == 1440:
        return "d"
    elif minutes >= 60:
        hours = minutes // 60
        return f"h{hours}"
    return f"m{minutes}"


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Lấy danh sách providers từ DB
# ─────────────────────────────────────────────────────────────────────────────

def get_all_providers() -> List[str]:
    """Query tất cả provider_code từ bảng dbo.providers."""
    if db_engine is None:
        logger.error("[Backfill] DB engine chưa khởi tạo")
        return []
    try:
        with db_engine.connect() as conn:
            result = conn.execute(sql_text("SELECT provider_code FROM dbo.providers"))
            providers = [row[0] for row in result if row[0]]
        logger.info(f"[Backfill] Tìm thấy {len(providers)} provider(s): {providers}")
        return providers
    except Exception as e:
        logger.error(f"[Backfill] Lỗi query providers: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Đọc strategy_list.json → targets
# ─────────────────────────────────────────────────────────────────────────────

def get_backfill_targets(config_path: str = CONFIG_PATH) -> List[Dict[str, str]]:
    """
    Đọc strategy_list.json → trả về danh sách (symbol, timeframe) cần backfill.
    Chỉ lấy từ strategy đang enabled, loại bỏ trùng lặp.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            configs = json.load(f)
    except Exception as e:
        logger.error(f"[Backfill] Không đọc được {config_path}: {e}")
        return []

    seen = set()
    targets = []

    for cfg in configs:
        if not cfg.get("enabled", False):
            continue

        symbols = cfg.get("symbols", [])
        timeframes = cfg.get("timeframes", [])

        if symbols == "all" or timeframes == "all":
            logger.warning(
                f"[Backfill] Strategy '{cfg.get('name')}' dùng 'all' — bỏ qua."
            )
            continue

        if not isinstance(symbols, list) or not isinstance(timeframes, list):
            continue

        for sym in symbols:
            for tf in timeframes:
                key = f"{sym}:{tf}"
                if key not in seen:
                    seen.add(key)
                    targets.append({"symbol": str(sym), "timeframe": str(tf)})

    return targets


# ─────────────────────────────────────────────────────────────────────────────
# Redis helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_redis_existing(client, provider: str, symbol: str, timeframe: str) -> Set[str]:
    """Lấy set datetime strings đã có trong Redis list."""
    bucket_list_key = f"candle:{provider}:{symbol}:{timeframe}"
    raw = client.lrange(bucket_list_key, 0, -1)
    return set(
        dt.decode("utf-8") if isinstance(dt, bytes) else str(dt)
        for dt in raw
    )


def _add_missing_candles(
    client, provider: str, symbol: str, timeframe: str,
    df: pd.DataFrame, missing_dts: Set[str]
) -> int:
    """Ghi nến thiếu vào Redis dạng HASH."""
    if df is None or df.empty or not missing_dts:
        return 0

    pipe = client.pipeline(transaction=False)
    added = 0

    for _, row in df.iterrows():
        dt = row.get("date_time")
        if pd.isna(dt):
            continue
        if not isinstance(dt, datetime):
            try:
                dt = pd.to_datetime(dt).to_pydatetime()
            except Exception:
                continue
        dt = _ensure_utc(dt)
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        if dt_str not in missing_dts:
            continue

        ts_ms = int(dt.timestamp() * 1000)

        close_time = row.get("close_time")
        close_time_str = ""
        if close_time is not None and not pd.isna(close_time):
            try:
                if not isinstance(close_time, datetime):
                    close_time = pd.to_datetime(close_time).to_pydatetime()
                close_time = _ensure_utc(close_time)
                close_time_str = close_time.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                close_time_str = ""

        candle_key = f"candle:{provider}:{symbol}:{timeframe}:{dt_str}"
        mapping = {
            "date_time":   dt_str,
            "close_time":  close_time_str,
            "open":        str(row.get("open", "")),
            "high":        str(row.get("high", "")),
            "low":         str(row.get("low", "")),
            "close":       str(row.get("close", "")),
            "volume":      str(row.get("volume", "")),
            "timestampMs": str(ts_ms),
        }
        pipe.hset(candle_key, mapping=mapping)
        added += 1

    pipe.execute()
    return added


def _rebuild_list(client, provider: str, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
    """Rebuild list key từ DF — đảm bảo thứ tự DESC (newest first)."""
    bucket_list_key = f"candle:{provider}:{symbol}:{timeframe}"
    client.delete(bucket_list_key)

    # Sort ASC rồi LPUSH → list sẽ có thứ tự DESC
    sorted_dts = (
        df.sort_values("date_time", ascending=True)["date_time"]
        .dt.strftime("%Y-%m-%d %H:%M:%S")
        .tolist()
    )
    if sorted_dts:
        pipe = client.pipeline(transaction=False)
        for dt_str in sorted_dts:
            pipe.lpush(bucket_list_key, dt_str)
        pipe.execute()


def _trim_to_limit(client, provider: str, symbol: str, timeframe: str, limit: int) -> int:
    """Trim list và xóa HASH cũ, chỉ giữ tối đa `limit` nến mới nhất."""
    bucket_list_key = f"candle:{provider}:{symbol}:{timeframe}"
    current_len = client.llen(bucket_list_key)
    if current_len <= limit:
        return 0

    excess = current_len - limit
    old_dts = client.rpop(bucket_list_key, excess)
    if not old_dts:
        return 0

    pipe = client.pipeline(transaction=False)
    for dt in old_dts:
        dt_str = dt.decode("utf-8") if isinstance(dt, bytes) else str(dt)
        candle_key = f"candle:{provider}:{symbol}:{timeframe}:{dt_str}"
        pipe.delete(candle_key)
    pipe.execute()

    return excess


# ─────────────────────────────────────────────────────────────────────────────
# Main backfill logic
# ─────────────────────────────────────────────────────────────────────────────

def run_backfill(
    provider: str = "all",
    limit: int = DEFAULT_LIMIT,
    config_path: str = CONFIG_PATH,
) -> None:
    """Chạy backfill candle cho tất cả (provider, symbol, timeframe)."""

    # Xác định danh sách providers
    if provider.lower() == "all":
        providers = get_all_providers()
        if not providers:
            logger.error("[Backfill] Không tìm thấy provider nào. Dừng lại.")
            return
    else:
        providers = [provider]

    logger.info("=" * 70)
    logger.info("BẮT ĐẦU BACKFILL CANDLE")
    logger.info(f"Provider(s): {providers} | Limit: {limit} nến")
    logger.info("=" * 70)

    start_time = time.time()

    # Lấy targets từ config
    targets = get_backfill_targets(config_path)
    if not targets:
        logger.warning("[Backfill] Không có target nào. Dừng lại.")
        return

    logger.info(f"[Backfill] {len(targets)} target(s) x {len(providers)} provider(s)")
    for t in targets:
        logger.info(f"  - {t['symbol']} / tf={t['timeframe']}")

    # Kết nối Redis
    client = create_redis_client(db=0)
    if client is None:
        logger.error("[Backfill] Không thể kết nối Redis. Dừng lại.")
        return

    total_added = 0
    total_trimmed = 0
    success_count = 0
    fail_count = 0

    try:
        job_num = 0
        total_jobs = len(providers) * len(targets)

        for prov in providers:
            for target in targets:
                job_num += 1
                symbol    = target["symbol"]
                timeframe = target["timeframe"]
                db_tf     = _convert_timeframe_for_db(timeframe)

                logger.info("-" * 50)
                logger.info(
                    f"[Backfill] [{job_num}/{total_jobs}] "
                    f"{prov}:{symbol}:{timeframe} — lấy {limit} nến..."
                )

                # 1. Query từ SQL DB
                df = get_candles(
                    symbol=symbol,
                    timeframe=db_tf,
                    provider=prov,
                    limit=limit,
                )

                if df.empty:
                    logger.warning(
                        f"[Backfill] Không có dữ liệu DB cho "
                        f"{prov}:{symbol}/{db_tf}. Bỏ qua."
                    )
                    fail_count += 1
                    continue

                logger.info(f"[Backfill] Đã lấy {len(df)} nến từ DB")

                # 2. Tìm date_time từ DB
                df["date_time"] = pd.to_datetime(df["date_time"])
                db_dts = set(
                    _ensure_utc(dt).strftime("%Y-%m-%d %H:%M:%S")
                    for dt in df["date_time"]
                    if not pd.isna(dt)
                )

                # 3. Tìm date_time đã có trong Redis
                redis_dts = _get_redis_existing(client, prov, symbol, timeframe)

                # 4. Tìm nến thiếu
                missing_dts = db_dts - redis_dts

                # Kiểm tra HASH bị mất (có trong list nhưng không có HASH)
                for dt_str in redis_dts:
                    candle_key = f"candle:{prov}:{symbol}:{timeframe}:{dt_str}"
                    if not client.exists(candle_key):
                        missing_dts.add(dt_str)
                        logger.warning(f"  HASH thiếu cho {dt_str}")

                if missing_dts:
                    logger.info(f"[Backfill] Tìm thấy {len(missing_dts)} nến thiếu")

                    added = _add_missing_candles(
                        client, prov, symbol, timeframe, df, missing_dts
                    )
                    total_added += added
                    logger.info(f"[Backfill] Đã ghi {added} candle HASH vào Redis")
                    print(f"  Added {added} candles for {prov}:{symbol}:tf={timeframe}")

                    # Rebuild list
                    _rebuild_list(client, prov, symbol, timeframe, df)
                    logger.info(f"[Backfill] Đã rebuild list key")
                else:
                    logger.info(f"[Backfill] Không có nến thiếu — đã đầy đủ")

                # 5. Trim giữ tối đa limit nến
                trimmed = _trim_to_limit(client, prov, symbol, timeframe, limit)
                total_trimmed += trimmed
                if trimmed > 0:
                    logger.info(f"[Backfill] Đã trim {trimmed} nến cũ")
                    print(f"  Trimmed {trimmed} old candles")

                success_count += 1

    except Exception as e:
        logger.error(f"[Backfill] Lỗi tổng thể: {e}", exc_info=True)

    finally:
        try:
            client.close()
        except Exception:
            pass

    # Báo cáo
    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.info("BACKFILL CANDLE HOÀN TẤT")
    logger.info(f"  Targets: {success_count} thành công / {fail_count} thất bại")
    logger.info(f"  Tổng candle thêm: {total_added}")
    logger.info(f"  Tổng candle trim: {total_trimmed}")
    logger.info(f"  Thời gian: {elapsed:.1f} giây")
    logger.info("=" * 70)
    print(f"\nDone. Added: {total_added}, Trimmed: {total_trimmed}, Time: {elapsed:.1f}s")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill candle data lên Redis từ SQL DB"
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"Số nến tối đa (mặc định {DEFAULT_LIMIT})"
    )
    parser.add_argument(
        "--provider", type=str, default="all",
        help='Provider code, vd "CAPITALCOM". Mặc định "all"'
    )
    parser.add_argument(
        "--config", type=str, default=CONFIG_PATH,
        help="Đường dẫn strategy_list.json"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_backfill(
        provider=args.provider,
        limit=args.limit,
        config_path=args.config,
    )
