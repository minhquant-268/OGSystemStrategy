# candle.py
# Vai trò: Định nghĩa schema/model của một cây nến (Candlestick)
# Là "hợp đồng dữ liệu" chuẩn cho toàn hệ thống, bất kể dữ liệu đến từ sàn nào.
#
# Các trường chuẩn:
#   date_time     : str  - thời gian mở nến (YYYY-MM-DD HH:MM:SS)
#   close_time    : str  - thời gian đóng nến
#   provider      : str  - nguồn dữ liệu (vd: CAPITALCOM, BINANCE)
#   symbol        : str  - mã tài sản (vd: BTCUSD, EURUSD)
#   timeframe     : str  - khung thời gian (vd: 5, 15, 60)
#   timestampMs   : int  - epoch milliseconds
#   open          : float
#   high          : float
#   low           : float
#   close         : float
#   volume        : float
