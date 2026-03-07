# keyspace_monitor.py
# Vai trò: Lắng nghe Redis Keyspace Notification (realtime)
# - Subscribe __keyspace@0__:candle:* để nhận event khi có nến mới
# - Parse key -> provider, symbol, timeframe, timestamp
# - Lấy toàn bộ bucket nến từ Redis -> dựng DataFrame
# - Gọi strategy_engine để tính signal
# - Gọi redis_publisher để đẩy OG/signal lên Redis
