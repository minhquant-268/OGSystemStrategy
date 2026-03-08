"""
cleanup_worker.py
=================
Background thread doc dep du lieu cu tren Redis dinh ky.

Trach nhiem:
    1. Chay moi 5 phut (300 giay) trong 1 daemon thread
    2. Scan tat ca list key pattern OG:* va signal:*
    3. Voi moi list co > max_items (1000):
       - rpop cac item cu nhat ra khoi list
       - Xoa hash key tuong ung (OG:{...}:{datetime} hoac signal:{...}:{datetime})
    4. Tim va xoa hash key "mo coi" (orphaned) — ton tai nhung khong nam trong list nao

Cau truc Redis:
    LIST:  OG:comboATR:CAPITALCOM:US30:10           -> [dt1, dt2, dt3, ...]
    HASH:  OG:comboATR:CAPITALCOM:US30:10:dt1       -> {field: value, ...}
    LIST:  signal:comboATR:CAPITALCOM:US30:10        -> [dt1, dt2, ...]
    HASH:  signal:comboATR:CAPITALCOM:US30:10:dt1    -> {field: value, ...}

Duoc dung boi:
    - main.py (khoi dong cleanup_thread)

Cach dung:
    import threading
    from src.core.cleanup_worker import run_periodic_cleanup

    stop_event = threading.Event()
    t = threading.Thread(target=run_periodic_cleanup, args=(stop_event,), daemon=True)
    t.start()

    # Khi can dung:
    stop_event.set()
    t.join(timeout=5)
"""

import logging
import time
from typing import Optional

from src.utils.connection.redis_connect import create_redis_client, scan_keys

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

MAX_ITEMS_PER_LIST = 1000        # So luong toi da giu lai trong moi list
CLEANUP_INTERVAL   = 300         # Thoi gian giua 2 lan cleanup (giay) = 5 phut
SCAN_BATCH_SIZE    = 500         # So luong key scan moi lan


# ─────────────────────────────────────────────────────────────────────────────
# Core logic
# ─────────────────────────────────────────────────────────────────────────────

def cleanup_old_data(max_items: int = MAX_ITEMS_PER_LIST) -> None:
    """
    Doc dep du lieu OG va signal cu tren Redis.

    Buoc 1: Scan tat ca list key matching OG:* va signal:*
    Buoc 2: Voi moi list co > max_items, xoa cac entry cu nhat:
            - rpop item cu ra khoi list
            - Delete hash key tuong ung
    Buoc 3: Tim orphaned hash key (ton tai nhung khong co trong list)
            va xoa chung
    """
    client = None
    try:
        client = create_redis_client(db=0)
        if client is None:
            logger.error("[Cleanup] Khong the ket noi Redis")
            return

        logger.info("[Cleanup] Bat dau doc dep du lieu cu...")

        patterns = ["OG:*", "signal:*"]

        for pattern in patterns:
            # Tim tat ca LIST key matching pattern (khong phai hash)
            list_keys = scan_keys(client, pattern, key_type="list")
            logger.info(f"[Cleanup] Pattern '{pattern}': tim thay {len(list_keys)} list(s)")

            for list_key in list_keys:
                try:
                    _cleanup_single_list(client, list_key, max_items)
                except Exception as e:
                    logger.error(f"[Cleanup] Loi xu ly list '{list_key}': {e}")

        logger.info("[Cleanup] Hoan thanh doc dep du lieu cu")

    except Exception as e:
        logger.error(f"[Cleanup] Loi tong the: {e}", exc_info=True)
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass


def _cleanup_single_list(client, list_key: str, max_items: int) -> None:
    """
    Doc dep 1 list key cu the:
    - Trim list xuong con max_items
    - Xoa hash key tuong ung cua cac item bi trim
    - Tim va xoa orphaned hash keys
    """
    current_len = client.llen(list_key)

    # ── Buoc 1: Trim neu qua dai ─────────────────────────────────────────
    if current_len > max_items:
        items_to_remove = current_len - max_items
        logger.info(
            f"[Cleanup] List '{list_key}': {current_len} items, "
            f"can xoa {items_to_remove} items cu"
        )

        removed = 0
        for _ in range(items_to_remove):
            old_value = client.rpop(list_key)
            if old_value:
                # Hash key = list_key:datetime
                old_hash_key = f"{list_key}:{old_value}"
                deleted = client.delete(old_hash_key)
                if deleted:
                    removed += 1

        if removed:
            logger.info(f"[Cleanup] Da xoa {removed} hash key cu tu '{list_key}'")

    # ── Buoc 2: Tim orphaned hash keys ────────────────────────────────────
    # Chi chay khi list co du nhieu items (tranh scan vo ich)
    current_len = client.llen(list_key)
    if current_len < 10:
        return

    # Lay tat ca datetime trong list hien tai
    list_items = client.lrange(list_key, 0, -1)
    valid_dates = set(list_items)

    # Scan tat ca hash key matching pattern
    hash_pattern = f"{list_key}:*"
    hash_keys = scan_keys(client, hash_pattern, key_type="hash")

    orphaned = []
    for hk in hash_keys:
        # Extract datetime tu hash key
        # list_key = "OG:comboATR:CAPITALCOM:US30:10"
        # hash_key = "OG:comboATR:CAPITALCOM:US30:10:2026-03-07 22:00:00"
        # datetime = "2026-03-07 22:00:00"
        prefix = list_key + ":"
        if hk.startswith(prefix):
            dt_part = hk[len(prefix):]
            if dt_part not in valid_dates:
                orphaned.append(hk)

    if orphaned:
        pipe = client.pipeline(transaction=False)
        for orphan_key in orphaned:
            pipe.delete(orphan_key)
        pipe.execute()
        logger.info(
            f"[Cleanup] Da xoa {len(orphaned)} orphaned hash key "
            f"tu '{list_key}'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: run_periodic_cleanup (chay trong thread rieng)
# ─────────────────────────────────────────────────────────────────────────────

def run_periodic_cleanup(
    stop_event,
    interval: int = CLEANUP_INTERVAL,
    max_items: int = MAX_ITEMS_PER_LIST,
) -> None:
    """
    Chay cleanup dinh ky trong background thread.

    Args:
        stop_event : threading.Event — set() de dung thread
        interval   : So giay giua 2 lan cleanup (mac dinh 300 = 5 phut)
        max_items  : So item toi da giu lai moi list (mac dinh 1000)
    """
    logger.info(
        f"[Cleanup] Thread khoi dong | "
        f"interval={interval}s | max_items={max_items}"
    )

    while not stop_event.is_set():
        try:
            cleanup_old_data(max_items=max_items)
        except Exception as e:
            logger.error(f"[Cleanup] Loi trong chu ky cleanup: {e}")

        # Cho interval giay, nhung check stop_event moi giay de co the dung nhanh
        for _ in range(interval):
            if stop_event.is_set():
                break
            time.sleep(1)

    logger.info("[Cleanup] Thread da dung")
