# signal.py
# Vai trò: Định nghĩa schema/model của một tín hiệu giao dịch (Signal)
# Được tạo ra bởi strategy_engine sau khi strategy tính toán xong.
#
# Các trường chuẩn:
#   date_time     : str   - thời gian nến tạo signal
#   close_time    : str
#   provider      : str
#   symbol        : str
#   timeframe     : str
#   timestampMs   : int
#   signal        : int   - 0=no signal, 1=BUY, 2=SELL
#   signalString  : str   - "BUY" | "SELL" | "UNKNOWN"
#   strategy      : str   - tên strategy (vd: comboATR, MAcrossover)
#   candle_key    : str   - Redis key của cây nến gốc
#   created_at    : str   - thời điểm tạo signal
#   open, high, low, close, volume : float
#   SMA, MACD, MACD_Signal, MACD_Hist, ATR : float  - giá trị indicator tại nến đó
#   entry         : float - giá vào lệnh
#   sl            : float - giá Stop Loss
#   tp            : float - giá Take Profit
#   sl_distance   : float - khoảng cách SL tính từ entry (pips/points)
#   tp_distance   : float - khoảng cách TP tính từ entry (pips/points)
