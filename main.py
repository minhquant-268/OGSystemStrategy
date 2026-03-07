# main.py - Entrypoint realtime (chạy liên tục theo nến mới)
# Vai trò:
#   1. Khởi động background thread cleanup (cleanup_worker)
#   2. Start keyspace_monitor để lắng nghe Redis Keyspace Notification
#   3. Với mỗi nến mới: keyspace_monitor -> strategy_engine -> redis_publisher
#
# Flow:
#   Redis Keyspace Notification (candle:*)
#       └── keyspace_monitor.py     (parse key, get bucket data)
#               └── strategy_engine.py  (load strategy_list.json, run strategies)
#                       └── redis_publisher.py  (write OG/signal hash, publish channel)
#
# Entry point: python main.py

import sys
import os

project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

# TODO: import và khởi động các thành phần
# from src.core.keyspace_monitor import start_monitor
# from src.core.cleanup_worker import start_cleanup_thread

if __name__ == "__main__":
    print("System Strategy - Realtime Mode")
    # start_cleanup_thread()
    # start_monitor()
