"""
redis_publisher.py
==================
Day ket qua signal tu strategy_engine len Redis.

Trach nhiem:
    1. Ghi OG hash: OG:{strategy}:{provider}:{symbol}:{tf}:{datetime}
       -> TAT CA nen (ke ca khong co signal) — phuc vu dashboard & backtest

    2. Ghi signal hash: signal:{strategy}:{provider}:{symbol}:{tf}:{datetime}
       -> CHI cac nen co signal (1=BUY, 2=SELL)

    3. Publish pub/sub channel: signals_channel:{strategy}:{provider}:{symbol}:{tf}
       -> Gui JSON payload ngay khi co signal — OF_ctrader lang nghe o day

    4. Maintain list key cho moi strategy/symbol/tf:
       - OG:{strategy}:{provider}:{symbol}:{tf}       (list chua date_time)
       - signal:{strategy}:{provider}:{symbol}:{tf}   (list chua date_time)
       -> De dashboard query toan bo lich su

Cach dung:
    from src.core.redis_publisher import publish_strategy_result
    from src.core.strategy_engine import StrategyResult

    # Sau khi engine chay xong
    for result in engine.run(df):
        publish_strategy_result(client, result, target_key="candle:...:2026-03-07 22:00:00")

Duoc goi boi:
    - src/core/keyspace_monitor.py  (realtime, khi co nen moi)
    - back_fill_og.py               (backfill, viet toan bo 1000 nen)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import redis

from src.utils.connection.redis_connect import hset_hash, lpush_list, publish_channel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Config — Cau truc output hash tren Redis
# ─────────────────────────────────────────────────────────────────────────────
#
# Payload ghi len Redis duoc chia lam 2 nhom:
#
# NHOM 1 — FIXED FIELDS (co dinh, strategy nao cung co, thu tu khong doi):
#   date_time, close_time, provider, symbol, timeframe, timestampMs,
#   signal, signalString, strategy, candle_key, created_at,
#   open, high, low, close, volume,
#   entry, sl, tp, sl_distance, tp_distance
#
# NHOM 2 — DYNAMIC INDICATOR FIELDS (tu dong lay tu DataFrame):
#   Moi strategy se tao ra cac cot indicator khac nhau:
#     comboATR    -> SMA, MACD, MACD_Signal, MACD_Hist, ATR
#     RSI         -> RSI, ATR
#     MACrossover -> MA_Short, MA_Long, ATR
#     (strategy moi) -> cot moi se TU DONG xuat hien o day
#
# => Khi them strategy moi, KHONG can sua file nay.
# ─────────────────────────────────────────────────────────────────────────────

# Cac truong OHLCV + entry/sl/tp co dinh (khong phai metadata, khong phai indicator)
# Duoc ghi SAU metadata, TRUOC indicator.
_FIXED_DATA_FIELDS = [
    "open", "high", "low", "close", "volume",
    "entry", "sl", "tp", "sl_distance", "tp_distance",
]

# Tap hop TAT CA fixed fields (metadata + data) — dung de loai bo khi lay dynamic
_ALL_FIXED_FIELDS = {
    "date_time", "close_time", "provider", "symbol", "timeframe",
    "timestampMs", "signal", "signalString", "strategy", "candle_key",
    "created_at",
    "open", "high", "low", "close", "volume",
    "entry", "sl", "tp", "sl_distance", "tp_distance",
}

# Cac truong khi vang mat se duoc dat "nan" (tranh OF_ctrader loi khi doc)
_NAN_FALLBACK_FIELDS = {"entry", "sl", "tp", "sl_distance", "tp_distance"}


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_dt_str(value) -> str:
    """Normalize datetime-like value thanh 'YYYY-mm-dd HH:MM:SS' UTC."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""

    dt = None
    try:
        s_iso = s.replace(",", ".")
        dt = datetime.fromisoformat(s_iso)
    except Exception:
        try:
            dt = pd.to_datetime(s, errors="coerce")
            if pd.isna(dt):
                dt = None
            else:
                dt = dt.to_pydatetime()
        except Exception:
            dt = None

    if not dt:
        return s

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _timestamp_to_ms_str(timestamp_str: str) -> str:
    """Convert timestamp string thanh milliseconds string."""
    if not timestamp_str:
        return ""
    s = str(timestamp_str).strip()
    if s.isdigit():
        return s
    dt_norm = _normalize_dt_str(s)
    try:
        dt = datetime.strptime(dt_norm, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc)
        return str(int(dt.timestamp() * 1000))
    except Exception:
        return ""


def _build_payload(
    row: pd.Series,
    provider: str,
    symbol: str,
    timeframe: str,
    strategy_name: str,
    candle_key: str,
) -> dict:
    """
    Xay dung payload dict tu 1 row DataFrame de ghi len Redis hash.
    Tat ca value duoc convert sang str (Redis hash chi chua string).
    """
    sig_val = 0
    try:
        sig_val = int(float(row.get("signal", 0)))
    except Exception:
        sig_val = 0

    # date_time
    dt_str = ""
    if "date_time" in row.index:
        dt_str = _normalize_dt_str(row["date_time"])

    # close_time
    close_time_str = ""
    if "close_time" in row.index:
        close_time_str = _normalize_dt_str(row["close_time"])

    # timestampMs
    ts_ms = ""
    if "timestampMs" in row.index:
        try:
            ts_ms = str(int(float(row["timestampMs"])))
        except Exception:
            ts_ms = _timestamp_to_ms_str(dt_str)
    else:
        ts_ms = _timestamp_to_ms_str(dt_str)

    # signal string
    sig_str = ""
    if sig_val == 1:
        sig_str = "BUY"
    elif sig_val == 2:
        sig_str = "SELL"

    payload = {
        "date_time"   : dt_str,
        "close_time"  : close_time_str,
        "provider"    : str(provider),
        "symbol"      : str(symbol),
        "timeframe"   : str(timeframe),
        "timestampMs" : ts_ms,
        "signal"      : str(sig_val),
        "signalString": sig_str,
        "strategy"    : strategy_name,
        "candle_key"  : candle_key,
        "created_at"  : datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3],
    }

    # ── NHOM 1b: OHLCV + entry/sl/tp (co dinh) ────────────────────────────
    for col in _FIXED_DATA_FIELDS:
        if col in row.index:
            val = row[col]
            payload[col] = "nan" if pd.isna(val) else str(val)
        elif col in _NAN_FALLBACK_FIELDS:
            payload[col] = "nan"

    # ── NHOM 2: DYNAMIC INDICATOR FIELDS ─────────────────────────────────
    # Lay TAT CA cot con lai tu row ma chua nam trong payload.
    # Day chinh la cac cot indicator do strategy tao ra
    # (SMA, MACD, RSI, BB_upper, ... tuy strategy).
    for col in row.index:
        if col in _ALL_FIXED_FIELDS:     # da xu ly o tren
            continue
        if col.startswith("_"):          # bo qua _key, _internal, ...
            continue
        if col in payload:               # da co roi (phong truong hop)
            continue
        val = row[col]
        payload[col] = "nan" if pd.isna(val) else str(val)

    return payload


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: Publish 1 StrategyResult (realtime — chi nen hien tai)
# ─────────────────────────────────────────────────────────────────────────────

def publish_strategy_result(
    client: redis.Redis,
    result,       # StrategyResult from strategy_engine
    target_key: str = "",
) -> None:
    """
    Ghi OG hash + signal hash cho NEN HIEN TAI (cay nen vua trigger).
    Dung trong realtime mode (keyspace_monitor).

    Args:
        client     : Redis client (DB0)
        result     : StrategyResult tu strategy_engine
        target_key : Key candle hien tai (vd "candle:CAPITALCOM:US30:10:2026-03-07 22:00:00")
                     Dùng de xac dinh dong nao trong df_result la nen dang xu ly.
                     Neu rong, lay nen cuoi cung.
    """
    strategy_name = result.strategy_name
    provider      = result.provider
    symbol        = result.symbol
    timeframe     = result.timeframe
    df            = result.df_result

    if df is None or df.empty or "signal" not in df.columns:
        return

    # Tim row cua nen hien tai
    row = None
    if target_key and "_key" in df.columns:
        matched = df[df["_key"] == target_key]
        if not matched.empty:
            row = matched.iloc[-1]

    if row is None:
        # Fallback: lay nen cuoi cung
        row = df.iloc[-1]

    try:
        sig_val = int(float(row.get("signal", 0)))
    except Exception:
        sig_val = 0

    dt_for_key = ""
    if "date_time" in row.index:
        dt_for_key = _normalize_dt_str(row["date_time"])
    if not dt_for_key:
        # Fallback: lay tu target_key
        parts = target_key.split(":") if target_key else []
        if len(parts) >= 5:
            dt_for_key = ":".join(parts[4:])

    if not dt_for_key:
        logger.warning(
            f"[Publisher][{strategy_name}] Khong co date_time hop le "
            f"— khong the ghi OG/signal"
        )
        return

    candle_key = target_key or f"candle:{provider}:{symbol}:{timeframe}:{dt_for_key}"
    payload = _build_payload(row, provider, symbol, timeframe, strategy_name, candle_key)

    # ── 1. Ghi OG hash (tat ca nen, ke ca khong co signal) ────────────────
    og_key = f"OG:{strategy_name}:{provider}:{symbol}:{timeframe}:{dt_for_key}"

    if client.exists(og_key):
        logger.debug(f"[Publisher] OG key da ton tai, bo qua: {og_key}")
    else:
        hset_hash(client, og_key, payload)
        logger.info(f"[Publisher] Ghi OG: {og_key}")

        # Them vao list
        og_list_key = f"OG:{strategy_name}:{provider}:{symbol}:{timeframe}"
        lpush_list(client, og_list_key, dt_for_key)

    # ── 2. Ghi signal hash (chi khi co signal BUY/SELL) ───────────────────
    if sig_val in (1, 2):
        signal_key = f"signal:{strategy_name}:{provider}:{symbol}:{timeframe}:{dt_for_key}"

        if client.exists(signal_key):
            logger.debug(f"[Publisher] Signal key da ton tai, bo qua: {signal_key}")
        else:
            hset_hash(client, signal_key, payload)
            logger.info(
                f"[Publisher] === TIN HIEU === "
                f"{payload['signalString']} | {strategy_name} | "
                f"{provider}:{symbol}:{timeframe} | {dt_for_key}"
            )

            # Them vao signal list
            signal_list_key = f"signal:{strategy_name}:{provider}:{symbol}:{timeframe}"
            lpush_list(client, signal_list_key, dt_for_key)

            # ── 3. Publish pub/sub channel (CHI khi signal moi) ───────────
            channel = f"signals_channel:{strategy_name}:{provider}:{symbol}:{timeframe}"
            msg = json.dumps({"key": signal_key, "payload": payload})
            publish_channel(client, channel, msg)
            logger.info(f"[Publisher] Published -> {channel}")


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: Publish full DataFrame (backfill — tat ca nen)
# ─────────────────────────────────────────────────────────────────────────────

def publish_backfill(
    client: redis.Redis,
    result,         # StrategyResult
    max_per_list: int = 1000,
) -> int:
    """
    Ghi TOAN BO DataFrame cua 1 StrategyResult len Redis.
    Dung trong backfill mode (back_fill_og.py).

    Args:
        client       : Redis client (DB0)
        result       : StrategyResult tu strategy_engine
        max_per_list : So luong toi da giu trong list key

    Returns:
        So luong nen da ghi thanh cong
    """
    strategy_name = result.strategy_name
    provider      = result.provider
    symbol        = result.symbol
    timeframe     = result.timeframe
    df            = result.df_result

    if df is None or df.empty:
        return 0

    og_list_key     = f"OG:{strategy_name}:{provider}:{symbol}:{timeframe}"
    signal_list_key = f"signal:{strategy_name}:{provider}:{symbol}:{timeframe}"

    # Xoa list cu de thay the lich su (giong NP backfill)
    client.delete(og_list_key)
    client.delete(signal_list_key)

    pipe = client.pipeline(transaction=False)
    wrote = 0

    for _, row in df.iterrows():
        dt_str = _normalize_dt_str(row.get("date_time"))
        if not dt_str:
            continue

        candle_key = f"candle:{provider}:{symbol}:{timeframe}:{dt_str}"
        payload = _build_payload(row, provider, symbol, timeframe, strategy_name, candle_key)

        og_key = f"OG:{strategy_name}:{provider}:{symbol}:{timeframe}:{dt_str}"
        # Convert tat ca value sang str truoc khi ghi
        safe_payload = {k: str(v) for k, v in payload.items()}
        pipe.hset(og_key, mapping=safe_payload)
        pipe.lpush(og_list_key, dt_str)

        # Chi ghi signal hash khi co BUY/SELL
        try:
            sig = int(float(row.get("signal", 0)))
        except Exception:
            sig = 0

        if sig in (1, 2):
            signal_key = f"signal:{strategy_name}:{provider}:{symbol}:{timeframe}:{dt_str}"
            pipe.hset(signal_key, mapping=safe_payload)
            pipe.lpush(signal_list_key, dt_str)

        wrote += 1

    pipe.execute()

    # Trim list de giu toi da max_per_list
    try:
        client.ltrim(og_list_key, 0, max_per_list - 1)
        client.ltrim(signal_list_key, 0, max_per_list - 1)
    except Exception as e:
        logger.warning(f"[Publisher] Loi trim list: {e}")

    logger.info(
        f"[Publisher] Backfill xong | {strategy_name} | "
        f"{provider}:{symbol}:{timeframe} | {wrote} nen"
    )
    return wrote
