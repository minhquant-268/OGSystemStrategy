"""
back_fill_og.py — Backfill 1000 nen lich su len Redis
=====================================================
Chay 1 lan de khoi tao du lieu OG + signal tren Redis.

Flow:
    1. Doc strategy_list.json → lay danh sach (symbol, timeframe) can xu ly
    2. Voi moi (symbol, timeframe): query 1000 nen tu SQL Server (db_connect)
    3. Chay strategy_engine.run(df) → tinh signal
    4. Goi redis_publisher.publish_backfill() → ghi TOAN BO OG + signal len Redis

Dung de:
    - Khoi tao du lieu sau khi restart server
    - Dashboard co data lich su ngay lap tuc
    - Test strategy tren du lieu qua khu

Chay:
    python back_fill_og.py
    python back_fill_og.py --limit 500        # chi lay 500 nen
    python back_fill_og.py --provider CAPITALCOM  # chi 1 provider
"""

import os
import sys
import json
import argparse
import time
from typing import List, Dict

# Them project root vao sys.path
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from src.utils.logger import setup_logger, get_logger
from sqlalchemy import text as sql_text

from src.utils.connection.db_connect import get_candles, get_asset_provider_pairs, engine as db_engine
from src.utils.connection.redis_connect import create_redis_client
from src.core.strategy_engine import StrategyEngine
from src.core.redis_publisher import publish_backfill
from src.core.signal_filter import apply_knn_filter

logger = get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_LIMIT    = 1000
CONFIG_PATH      = os.path.join(project_root, "config", "strategy_list.json")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Lay danh sach providers tu DB
# ─────────────────────────────────────────────────────────────────────────────

def get_all_providers() -> List[str]:
    """
    Query tat ca provider_code tu bang dbo.providers trong SQL Server.

    Returns:
        List[str] — vd ["CAPITALCOM", "BINANCE", "BYBIT"]
        Tra ve list rong neu loi.
    """
    if db_engine is None:
        logger.error("[Backfill] DB engine chua khoi tao — khong the query providers")
        return []

    try:
        with db_engine.connect() as conn:
            result = conn.execute(sql_text("SELECT provider_code FROM dbo.providers"))
            providers = [row[0] for row in result if row[0]]
        logger.info(f"[Backfill] Tim thay {len(providers)} provider(s) trong DB: {providers}")
        return providers
    except Exception as e:
        logger.error(f"[Backfill] Loi query providers: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Doc strategy_list.json → lay tat ca (symbol, timeframe) duy nhat
# ─────────────────────────────────────────────────────────────────────────────

def get_backfill_targets(config_path: str = CONFIG_PATH) -> List[Dict[str, str]]:
    """
    Đọc strategy_list.json → Lấy danh sách symbols → Query DB để tìm (provider, symbol) pairs.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            configs = json.load(f)
    except Exception as e:
        logger.error(f"[Backfill] Không đọc được {config_path}: {e}")
        return []

    # 1. Thu thập tất cả symbols duy nhất từ config
    config_symbols = set()
    config_timeframes = {} # symbol -> set of timeframes

    for cfg in configs:
        if not cfg.get("enabled", False):
            continue
        
        symbols = cfg.get("symbols", [])
        timeframes = cfg.get("timeframes", [])
        
        if symbols == "all" or timeframes == "all":
            continue
            
        for sym in symbols:
            s_str = str(sym)
            config_symbols.add(s_str)
            if s_str not in config_timeframes:
                config_timeframes[s_str] = set()
            for tf in timeframes:
                config_timeframes[s_str].add(str(tf))

    if not config_symbols:
        return []

    # 2. Query DB để lấy các cặp (provider, symbol) hợp lệ
    pairs = get_asset_provider_pairs(list(config_symbols))
    
    # 3. Kết hợp với timeframes
    targets = []
    for p in pairs:
        symbol = p["symbol"]
        provider = p["provider"]
        if symbol in config_timeframes:
            for tf in config_timeframes[symbol]:
                targets.append({
                    "symbol": symbol,
                    "provider": provider,
                    "timeframe": tf
                })

    return targets


# ─────────────────────────────────────────────────────────────────────────────
# Main backfill logic
# ─────────────────────────────────────────────────────────────────────────────

def run_backfill(
    provider: str = "all",
    limit: int = DEFAULT_LIMIT,
    config_path: str = CONFIG_PATH,
) -> None:
    """
    Chay backfill cho tat ca (provider, symbol, timeframe).

    Args:
        provider    : Provider code, vd "CAPITALCOM"
                      Dung "all" de backfill tat ca providers trong DB.
        limit       : So nen toi da lay tu DB (mac dinh 1000)
        config_path : Duong dan strategy_list.json
    """
    # Xac dinh danh sach providers
    if provider.lower() == "all":
        providers = get_all_providers()
        if not providers:
            logger.error("[Backfill] Khong tim thay provider nao trong DB. Dung lai.")
            return
    else:
        providers = [provider]

    logger.info("=" * 70)
    logger.info("BAT DAU BACKFILL OG + SIGNAL")
    logger.info(f"Provider(s): {providers} | Limit: {limit} nen")
    logger.info("=" * 70)

    start_time = time.time()

    # 1. Lay danh sach targets tu config
    targets = get_backfill_targets(config_path)
    if not targets:
        logger.warning("[Backfill] Khong co target nao de backfill. Dung lai.")
        return

    logger.info(f"[Backfill] Tim thay {len(targets)} target(s) x {len(providers)} provider(s)")
    for t in targets:
        logger.info(f"  - {t['symbol']} / {t['timeframe']}")
    for p in providers:
        logger.info(f"  - Provider: {p}")

    # 2. Khoi tao engine + Redis client
    engine = StrategyEngine(config_path=config_path)

    client = create_redis_client(db=0)
    if client is None:
        logger.error("[Backfill] Khong the ket noi Redis. Dung lai.")
        return

    # 3. Xu ly tung (provider, symbol, timeframe)
    total_candles = 0
    total_signals = 0
    success_count = 0
    fail_count = 0

    try:
        job_num = 0
        total_jobs = len(providers) * len(targets)

        # TRUOC DAY: for prov in providers: for target in targets:
        # BAY GIO: targets da co "provider" tu DB
        for target in targets:
            job_num += 1
            prov      = target["provider"]
            symbol    = target["symbol"]
            timeframe = target["timeframe"]

            # Neu user co specify --provider thi chi backfill provider do
            if provider.lower() != "all" and prov.lower() != provider.lower():
                continue

            logger.info("-" * 50)
            logger.info(
                f"[Backfill] [{job_num}/{total_jobs}] "
                f"{prov}:{symbol}:{timeframe} — lay {limit} nen..."
            )

            # 3a. Query tu SQL DB
            db_timeframe = _convert_timeframe_for_db(timeframe)

            df = get_candles(
                symbol=symbol,
                timeframe=db_timeframe,
                provider=prov,
                limit=limit,
            )

            if df.empty:
                logger.warning(
                    f"[Backfill] Khong co du lieu DB cho "
                    f"{prov}:{symbol}/{db_timeframe}. Bo qua."
                )
                fail_count += 1
                continue

            # 3b. Them metadata de engine co the filter
            df["provider"]  = prov
            df["symbol"]    = symbol
            df["timeframe"] = timeframe  # Giu dinh dang goc tu config

            logger.info(f"[Backfill] Da lay {len(df)} nen tu DB")

            # 3c. Chay strategy engine
            results = engine.run(df)

            # 3c.5 Apply KNN Trend filter
            results = [apply_knn_filter(r) for r in results]

            if not results:
                logger.warning(
                    f"[Backfill] Engine khong tra ve ket qua cho "
                    f"{prov}:{symbol}/{timeframe}. Bo qua."
                )
                fail_count += 1
                continue

            # 3d. Publish len Redis
            for result in results:
                try:
                    wrote = publish_backfill(
                        client=client,
                        result=result,
                        max_per_list=limit,
                    )
                    total_candles += wrote

                    # Dem signal
                    if result.df_result is not None and "signal" in result.df_result.columns:
                        sig_count = (
                            result.df_result["signal"]
                            .apply(lambda x: int(float(x)) in (1, 2))
                            .sum()
                        )
                        total_signals += sig_count

                    logger.info(
                        f"[Backfill] Ghi {wrote} nen | "
                        f"Strategy: {result.strategy_name}"
                    )
                except Exception as e:
                    logger.error(
                        f"[Backfill] Loi publish {result.strategy_name}: {e}",
                        exc_info=True,
                    )

            success_count += 1

    except Exception as e:
        logger.error(f"[Backfill] Loi tong the: {e}", exc_info=True)

    finally:
        # Dong Redis client
        try:
            client.close()
        except Exception:
            pass

    # 4. Bao cao ket qua
    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.info("BACKFILL HOAN TAT")
    logger.info(f"  Targets: {success_count} thanh cong / {fail_count} that bai")
    logger.info(f"  Tong OG : {total_candles} nen")
    logger.info(f"  Tong signal: {total_signals} tin hieu")
    logger.info(f"  Thoi gian: {elapsed:.1f} giay")
    logger.info("=" * 70)


def _convert_timeframe_for_db(tf: str) -> str:
    """
    Convert timeframe tu config format sang DB format.
    Config: "10", "15", "60", "240"
    DB:     "m10", "m15", "h1", "h4"

    Rules:
        < 60    → "m{tf}"     (phut)
        >= 60   → "h{tf/60}"  (gio)
        1440    → "d"         (ngay)
    """
    try:
        minutes = int(tf)
    except (ValueError, TypeError):
        # Neu da co prefix (m10, h1) → giu nguyen
        return tf

    if minutes < 60:
        return f"m{minutes}"
    elif minutes == 1440:
        return "d"
    elif minutes >= 60:
        hours = minutes // 60
        return f"h{hours}"
    return f"m{minutes}"


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill OG + signal data len Redis tu SQL DB"
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"So nen toi da lay tu DB (mac dinh {DEFAULT_LIMIT})"
    )
    parser.add_argument(
        "--provider", type=str, default="all",
        help='Provider code, vd "CAPITALCOM". Mac dinh "all" = tat ca providers trong DB'
    )
    parser.add_argument(
        "--config", type=str, default=CONFIG_PATH,
        help="Duong dan strategy_list.json"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_backfill(
        provider=args.provider,
        limit=args.limit,
        config_path=args.config,
    )
