"""
keyspace_monitor.py
===================
Lang nghe Redis Keyspace Notification (realtime).

Flow:
    1. Subscribe __keyspace@0__:candle:* de nhan event khi co nen moi (hset)
    2. Parse key -> provider, symbol, timeframe, timestamp
    3. Doc TOAN BO bucket nen tu Redis (candle:{provider}:{symbol}:{tf}:*)
    4. Dung DataFrame OHLCV
    5. Goi strategy_engine.run(df) de tinh signal
    6. Goi redis_publisher.publish_strategy_result() cho tung ket qua

Duoc goi boi:
    - main.py (entry point)

QUAN TRONG:
    - Module nay KHONG import indicator hay strategy truc tiep
    - No chi giao tiep voi strategy_engine (dieu phoi) va redis_publisher (day len Redis)
"""

import logging
import time
from typing import Optional

import pandas as pd
import redis

from src.utils.connection.redis_connect import (
    get_redis_client,
    close_redis_client,
    get_candle_bucket,
    enable_keyspace_notifications,
)
from src.core.strategy_engine import StrategyEngine
from src.core.redis_publisher import publish_strategy_result

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_candle_key(key: str) -> dict:
    """
    Parse candle key thanh cac thanh phan.

    Input:  "candle:CAPITALCOM:BTCUSD:15:2026-03-07 22:00:00"
    Output: {"provider": "CAPITALCOM", "symbol": "BTCUSD",
             "timeframe": "15", "timestamp": "2026-03-07 22:00:00"}

    Luu y: timestamp co the chua ':' (HH:MM:SS) nen phai join lai
    cac phan tu tu index 4 tro di.
    """
    parts = str(key).split(":")
    if len(parts) < 5 or parts[0] != "candle":
        return {}
    return {
        "provider"  : parts[1],
        "symbol"    : parts[2],
        "timeframe" : parts[3],
        "timestamp" : ":".join(parts[4:]),
    }


def _build_df_from_bucket(records: list) -> pd.DataFrame:
    """
    Build DataFrame tu danh sach records doc tu Redis bucket.
    Convert OHLCV sang float, sort theo date_time hoac timestampMs.
    """
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Convert OHLCV sang float
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert timestampMs
    if "timestampMs" in df.columns:
        df["timestampMs"] = pd.to_numeric(df["timestampMs"], errors="coerce")

    # Convert date_time
    if "date_time" in df.columns:
        df["date_time"] = pd.to_datetime(df["date_time"], errors="coerce")

    # Sort theo thoi gian
    if "date_time" in df.columns:
        df = df.sort_values("date_time").reset_index(drop=True)
    elif "timestampMs" in df.columns:
        df = df.sort_values("timestampMs").reset_index(drop=True)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: handle_candle_event
# ─────────────────────────────────────────────────────────────────────────────

def handle_candle_event(
    client: redis.Redis,
    engine: StrategyEngine,
    provider: str,
    symbol: str,
    timeframe: str,
    timestamp: str,
    candle_key: str,
) -> None:
    """
    Xu ly 1 event candle: doc bucket -> chay strategy -> ghi OG/signal.

    Args:
        client     : Redis client (DB0)
        engine     : StrategyEngine da load config
        provider   : Provider code, vd "CAPITALCOM"
        symbol     : Symbol code, vd "US30"
        timeframe  : Timeframe (minute string), vd "10"
        timestamp  : Timestamp string cua nen hien tai
        candle_key : Full Redis key cua nen hien tai
    """
    try:
        # 1. Doc toan bo nen tu bucket
        records = get_candle_bucket(client, provider, symbol, timeframe)
        if not records:
            logger.warning(
                f"[Monitor] Khong co nen trong bucket "
                f"candle:{provider}:{symbol}:{timeframe}"
            )
            return

        # 2. Build DataFrame
        df = _build_df_from_bucket(records)
        if df.empty:
            return

        # Them metadata de engine co the filter
        df["provider"]  = provider
        df["symbol"]    = symbol
        df["timeframe"] = timeframe

        logger.info(
            f"[Monitor] Bucket {provider}:{symbol}:{timeframe} | "
            f"{len(df)} nen | Nen hien tai: {timestamp}"
        )

        # 3. Chay strategy engine
        results = engine.run(df)

        # 4. Publish ket qua
        for result in results:
            try:
                publish_strategy_result(
                    client=client,
                    result=result,
                    target_key=candle_key,
                )
            except Exception as e:
                logger.error(
                    f"[Monitor] Loi publish {result.strategy_name}: {e}",
                    exc_info=True,
                )

    except Exception as e:
        logger.error(
            f"[Monitor] Loi xu ly event {candle_key}: {e}",
            exc_info=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: monitor_keyspace_notifications (main loop)
# ─────────────────────────────────────────────────────────────────────────────

def monitor_keyspace_notifications(
    engine: Optional[StrategyEngine] = None,
    config_path: str = "config/strategy_list.json",
) -> None:
    """
    Vong lap chinh — subscribe Redis Keyspace va xu ly event candle.

    Args:
        engine      : StrategyEngine da khoi tao (None = tu tao moi)
        config_path : Duong dan config (chi dung khi engine=None)

    Raises:
        KeyboardInterrupt  : Khi user nhan Ctrl+C
        ConnectionError    : Khi mat ket noi Redis
    """
    logger.info("=" * 70)
    logger.info("[Monitor] KHOI DONG REDIS KEYSPACE MONITOR")
    logger.info("=" * 70)

    # Khoi tao engine neu chua co
    if engine is None:
        engine = StrategyEngine(config_path=config_path)

    # Ket noi Redis
    client = get_redis_client()
    if not client:
        logger.error("[Monitor] Khong the ket noi Redis — dung lai.")
        return

    # Bat keyspace notifications
    enable_keyspace_notifications(client, events="KEA")

    # Subscribe pattern
    pubsub = client.pubsub()
    pubsub.psubscribe("__keyspace@0__:candle:*")
    logger.info("[Monitor] Subscribed: __keyspace@0__:candle:*")
    logger.info("[Monitor] Dang cho event nen moi... (Ctrl+C de dung)")

    try:
        for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue

            channel = message["channel"]
            event   = message["data"]

            # Chi xu ly event hset (khi co nen moi duoc ghi/cap nhat)
            if event not in ("hset", "set"):
                continue

            # Parse key
            key = channel.replace("__keyspace@0__:", "")
            parsed = _parse_candle_key(key)
            if not parsed:
                continue

            provider  = parsed["provider"]
            symbol    = parsed["symbol"]
            timeframe = parsed["timeframe"]
            timestamp = parsed["timestamp"]

            logger.info(
                f"[Monitor] Event: {event} | "
                f"{provider}:{symbol}:{timeframe} | {timestamp}"
            )

            # Xu ly event
            handle_candle_event(
                client=client,
                engine=engine,
                provider=provider,
                symbol=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                candle_key=key,
            )

    except KeyboardInterrupt:
        logger.info("[Monitor] Dung boi nguoi dung (Ctrl+C)")
        raise
    except redis.exceptions.ConnectionError as e:
        logger.error(f"[Monitor] Mat ket noi Redis: {e}")
        raise
    except Exception as e:
        logger.error(f"[Monitor] Loi: {e}", exc_info=True)
        raise
    finally:
        try:
            pubsub.punsubscribe()
            pubsub.close()
        except Exception:
            pass
