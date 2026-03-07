# helpers.py
# Vai trò: Các hàm tiện ích nhỏ dùng chung toàn dự án
# - normalize_dt_str(value) -> str          : Chuẩn hóa datetime string về 'YYYY-MM-DD HH:MM:SS'
# - timestamp_to_ms(dt_str) -> int          : Convert datetime string -> epoch milliseconds
# - extract_timestamp_from_key(key) -> str  : Lấy phần timestamp từ Redis candle key
