"""
main.py — Entry point (realtime mode)
=====================================
Ket noi tat ca module thanh he thong hoan chinh:

    1. Setup logging (file + console)
    2. Disable Quick Edit Mode (Windows)
    3. Khoi dong cleanup_worker thread (daemon, moi 5 phut)
    4. Khoi dong keyspace_monitor (vong lap chinh, lang nghe Redis)
       - Khi co nen moi: monitor -> strategy_engine -> redis_publisher
       - Mat ket noi Redis: retry sau 5 giay
       - Ctrl+C: dung sach

Flow:
    Redis Keyspace Notification (candle:*)
        |-- keyspace_monitor.py  (parse key, get bucket data, build df)
        |       |-- strategy_engine.py (load config, filter, calculate_signals)
        |               |-- redis_publisher.py (write OG/signal hash, publish channel)
        |
        +-- cleanup_worker.py (background thread, trim old data moi 5 phut)

Chay:
    python main.py
"""

import os
import sys
import time
import platform
import threading
import logging

# Them project root vao sys.path de import src.*
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from src.utils.logger import setup_logger, get_logger
from src.core.strategy_engine import StrategyEngine
from src.core.keyspace_monitor import monitor_keyspace_notifications
from src.core.cleanup_worker import run_periodic_cleanup
from src.utils.connection.redis_connect import close_redis_client

import redis


# ─────────────────────────────────────────────────────────────────────────────
# Windows Quick Edit Mode fix
# ─────────────────────────────────────────────────────────────────────────────

def disable_quick_edit_mode() -> bool:
    """
    Tat Quick Edit Mode tren Windows de tranh pause khi click vao console.
    Tren Linux/Mac: khong lam gi.
    """
    if platform.system() != "Windows":
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        STD_INPUT_HANDLE = -10
        h_stdin = kernel32.GetStdHandle(STD_INPUT_HANDLE)

        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(h_stdin, ctypes.byref(mode))

        ENABLE_QUICK_EDIT   = 0x0040
        ENABLE_INSERT_MODE  = 0x0020
        ENABLE_EXTENDED_FLAGS = 0x0080

        new_mode = mode.value & ~ENABLE_QUICK_EDIT & ~ENABLE_INSERT_MODE
        new_mode |= ENABLE_EXTENDED_FLAGS

        kernel32.SetConsoleMode(h_stdin, new_mode)
        return True
    except Exception as e:
        print(f"Warning: Could not disable Quick Edit Mode: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Main function — khoi dong toan bo he thong."""

    # Setup logger
    logger = get_logger()

    # Banner
    logger.info("=" * 70)
    logger.info("KHOI DONG SYSTEM STRATEGY — REALTIME MODE")
    logger.info("Theo doi thay doi du lieu nen va phat hien tin hieu")
    logger.info("Nhan Ctrl+C de dung chuong trinh")
    logger.info("=" * 70)

    # Load strategy engine
    config_path = os.path.join(project_root, "config", "strategy_list.json")
    engine = StrategyEngine(config_path=config_path)

    # Cleanup thread
    stop_event = threading.Event()
    cleanup_thread = threading.Thread(
        target=run_periodic_cleanup,
        args=(stop_event,),
        daemon=True,
        name="CleanupThread",
    )

    try:
        # Start cleanup thread
        cleanup_thread.start()
        logger.info("Cleanup thread da khoi dong (chay moi 5 phut)")

        # Keyspace monitor loop (auto-retry khi mat ket noi)
        while True:
            try:
                monitor_keyspace_notifications(engine=engine, config_path=config_path)
                # Neu thoat binh thuong -> break
                break

            except KeyboardInterrupt:
                logger.info("=" * 70)
                logger.info("CHUONG TRINH DUOC DUNG BOI NGUOI DUNG (Ctrl+C)")
                logger.info("Logs da luu: system_strategy.log")
                logger.info("=" * 70)
                break

            except redis.exceptions.ConnectionError as e:
                logger.error(
                    f"Mat ket noi Redis: {e}. Thu ket noi lai sau 5 giay..."
                )
                close_redis_client()
                time.sleep(5)

            except Exception as e:
                logger.error(f"Loi khong mong muon: {e}", exc_info=True)
                break

            finally:
                close_redis_client()

    finally:
        # Dung cleanup thread
        if cleanup_thread.is_alive():
            logger.info("Dang dung cleanup thread...")
            stop_event.set()
            cleanup_thread.join(timeout=5)
            if cleanup_thread.is_alive():
                logger.warning("Cleanup thread khong dung trong thoi gian cho")
            else:
                logger.info("Cleanup thread da dung")

        # Dong Redis connection
        close_redis_client()
        logger.info("Da dong tat ca ket noi. Tam biet!")


if __name__ == "__main__":
    disable_quick_edit_mode()
    main()
