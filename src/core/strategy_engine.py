# strategy_engine.py
# Vai trò: Engine trung tâm điều phối việc chạy các strategy
# - Load danh sách strategy từ config/strategy_list.json
# - Nhận dữ liệu nến (DataFrame) từ keyspace_monitor hoặc backfill
# - Chạy từng strategy đã được bật (enabled=True) theo symbol/timeframe
# - Trả về danh sách kết quả signal để redis_publisher xử lý tiếp
