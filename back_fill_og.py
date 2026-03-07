# back_fill_og.py - Entrypoint backfill (chạy 1 lần với 1000 nến gần nhất)
# Vai trò:
#   Lấy 1000 nến lịch sử gần nhất từ SQL DB cho mỗi (symbol, timeframe)
#   được cấu hình trong config/strategy_list.json, chạy qua strategy_engine,
#   và đẩy toàn bộ kết quả OG + signal lên Redis.
#
# Dùng để:
#   - Khởi động lại hệ thống sau khi restart để có sẵn dữ liệu lịch sử
#   - Dashboard có thể query OG history ngay lập tức
#
# Entry point: python back_fill_og.py

import sys
import os

project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

# TODO: implement backfill logic
# from src.core.strategy_engine import run_strategy_on_df
# from utils.db_connect import get_candles
# from src.core.redis_publisher import publish_og, publish_signal

if __name__ == "__main__":
    print("System Strategy - Backfill Mode (1000 candles)")
