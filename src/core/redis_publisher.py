# redis_publisher.py
# Vai trò: Đẩy kết quả signal từ strategy_engine lên Redis
# - Ghi OG hash: OG:{strategy}:{provider}:{symbol}:{tf}:{datetime}  (tất cả nến)
# - Ghi signal hash: signal:{strategy}:{provider}:{symbol}:{tf}:{datetime}  (chỉ nến có signal)
# - Publish pub/sub channel: signals_channel:{strategy}:{provider}:{symbol}:{tf}
# - Maintain list key cho mỗi strategy/symbol/tf để tiện dashboard query
