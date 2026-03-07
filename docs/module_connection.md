# Module Connection — Tài Liệu Triển Khai

> **Module**: Connection Layer  
> **Vị trí**: `src/utils/connection/`  
> **Ngày tạo**: 2026-03-07  
> **Trạng thái**: ✅ Hoàn thành — Sẵn sàng test

---

## 1. Tổng Quan

Module Connection là **tầng hạ tầng (infrastructure layer)** — đóng gói toàn bộ logic kết nối tới SQL Server và Redis. Các module bên trên (`core/`, `strategies/`) **không bao giờ gọi thẳng pyodbc hay redis-py** mà chỉ gọi qua các hàm trong module này.

```
Các module bên trên                   Module Connection
─────────────────────────────────     ────────────────────────────
src/core/keyspace_monitor.py      →   redis_connect.get_redis_client()
src/core/redis_publisher.py       →   redis_connect.hset_hash()
src/core/cleanup_worker.py        →   redis_connect.scan_keys()
back_fill_og.py                   →   db_connect.get_candles()
                                      redis_connect.hset_hash()
```

---

## 2. Files

| File | Vai trò |
|---|---|
| `src/utils/connection/redis_connect.py` | Kết nối Redis, cung cấp singleton client và helper functions |
| `src/utils/connection/db_connect.py` | Kết nối SQL Server, cung cấp `get_candles()` trả về DataFrame |
| `.env` | Biến môi trường: host, port, credentials |
| `tests/test_connection.py` | Manual test runner — kiểm tra kết nối thực tế |

---

## 3. Cấu Hình (.env)

```env
# SQL Server
DB_SERVER=10.11.12.6
DB_NAME=TradingDB
DB_USER=trading_user2
DB_PASSWORD=abc@123
DB_DRIVER=ODBC Driver 17 for SQL Server

# Redis
REDIS_HOST=10.11.12.8
REDIS_PORT=6379
REDIS_PASSWORD=abc@123
```

> [!CAUTION]
> File `.env` chứa credentials thật — **đã thêm vào `.gitignore`**, không được push lên Git.

---

## 4. SQL DB (`db_connect.py`)

### 4.1 Hàm chính

```python
from src.utils.connection.db_connect import test_connection, get_candles

# Kiểm tra kết nối
ok = test_connection()  # → True / False

# Lấy dữ liệu nến
df = get_candles(
    symbol="BTCUSD",
    timeframe="m10",        # phải match tên bảng tvc.m10
    provider="CAPITALCOM",
    limit=1000              # lấy 1000 nến gần nhất
)
```

### 4.2 DataFrame trả về

| Cột | Kiểu | Mô tả |
|---|---|---|
| `date_time` | datetime | Thời gian mở nến |
| `close_time` | datetime | Thời gian đóng nến (tự tính = date_time nến tiếp theo) |
| `provider` | str | Provider code |
| `symbol` | str | Symbol code |
| `timeframe` | str | Timeframe string |
| `open` | float | Giá mở |
| `high` | float | Giá cao nhất |
| `low` | float | Giá thấp nhất |
| `close` | float | Giá đóng |
| `volume` | float | Khối lượng |

### 4.3 DB Schema (tham chiếu)

```sql
-- Bảng nến theo timeframe (tvc.m10, tvc.m15, tvc.h1, ...)
SELECT date_time, open, high, low, close, volume
FROM tvc.{timeframe}
WHERE asset_id = (SELECT asset_id FROM dbo.assets WHERE symbol = ? AND provider = ?)
  AND timeframe_id = (SELECT timeframe_id FROM dbo.timeframe WHERE timeframe_type = ?)
ORDER BY date_time DESC
```

---

## 5. Redis (`redis_connect.py`)

### 5.1 Client management

```python
from src.utils.connection.redis_connect import (
    get_redis_client,       # Singleton client (dùng lại)
    create_redis_client,    # Factory — khi cần client riêng
    close_redis_client,     # Đóng singleton khi shutdown
)

# Singleton — dùng trong hầu hết trường hợp
client = get_redis_client(db=0)

# Factory — cleanup_worker cần client riêng tách biệt
worker_client = create_redis_client(db=0)
```

### 5.2 Helper functions

```python
from src.utils.connection.redis_connect import (
    scan_keys,
    get_candle_bucket,
    hset_hash,
    lpush_list,
    publish_channel,
    enable_keyspace_notifications,
)

# Lấy tất cả nến của 1 symbol/timeframe
records = get_candle_bucket(client, "CAPITALCOM", "BTCUSD", "10")
# → List[Dict] mỗi dict là 1 nến, có thêm field "_key"

# Ghi hash (OG hoặc signal)
hset_hash(client, "OG:comboATR:CAPITALCOM:BTCUSD:10:2026-03-07 22:00:00", payload_dict)

# Thêm vào list (index)
lpush_list(client, "OG:comboATR:CAPITALCOM:BTCUSD:10", "2026-03-07 22:00:00")

# Publish signal
publish_channel(client, "signals_channel:comboATR:CAPITALCOM:BTCUSD:10", json_str)

# Scan keys an toàn (không block Redis)
keys = scan_keys(client, "OG:comboATR:*", key_type="hash")

# Bật keyspace notification (gọi 1 lần khi start)
enable_keyspace_notifications(client, events="KEA")
```

### 5.3 Redis Key Convention

| Pattern | Type | Ghi bởi | Đọc bởi |
|---|---|---|---|
| `candle:{provider}:{symbol}:{tf}:{dt}` | Hash | Module 2 (Data Feeder) | keyspace_monitor |
| `OG:{strategy}:{provider}:{symbol}:{tf}:{dt}` | Hash | redis_publisher | Dashboard, OF_ctrader |
| `OG:{strategy}:{provider}:{symbol}:{tf}` | List | redis_publisher | Dashboard query |
| `signal:{strategy}:{provider}:{symbol}:{tf}:{dt}` | Hash | redis_publisher | OF_ctrader |
| `signals_channel:{strategy}:{provider}:{symbol}:{tf}` | Pub/Sub | redis_publisher | OF_ctrader (subscribe) |

---

## 6. Chạy Test

```bash
# Di chuyển vào thư mục dự án
cd "c:\Users\Administrator\Desktop\sen15_by_NP\system revise\system_strategy_revise"

# Chạy test thủ công
python tests/test_connection.py
```

### Kết quả mong đợi khi PASS

```
████████████████████████████████████████████████████████████
  MODULE CONNECTION — Manual Test Runner
████████████████████████████████████████████████████████████

══════════════════════════════════════════════════════════════
TEST 1.1 — SQL Server Connection
══════════════════════════════════════════════════════════════
  ✅ PASS — Kết nối SQL Server thành công

TEST 1.2 — get_candles(BTCUSD, m10, CAPITALCOM, limit=50)
  ✅ PASS — Query OK, nhận được 50 nến

══════════════════════════════════════════════════════════════
TEST 2.1 — Redis Connection
══════════════════════════════════════════════════════════════
  ✅ PASS — Kết nối Redis thành công

TEST 2.2 — hset_hash        ✅ PASS
TEST 2.3 — scan_keys        ✅ PASS
TEST 2.4 — candle_bucket    ✅ PASS
TEST 2.5 — publish_channel  ✅ PASS
TEST 2.6 — cleanup          ✅ PASS

══════════════════════════════════════════════════════════════
  PASS: 8 | FAIL: 0 | SKIP: 0
══════════════════════════════════════════════════════════════
```

### Xử lý khi FAIL

| Lỗi | Nguyên nhân | Cách fix |
|---|---|---|
| DB Connection FAIL | Sai host/port/credentials | Kiểm tra `.env` DB_* |
| DB get_candles rỗng | Bảng tvc.m10 chưa có data hoặc sai symbol | Kiểm tra DB schema |
| Redis FAIL | Redis server chưa chạy | Kiểm tra `.env` REDIS_* |
| `candle:*` bucket rỗng | Module 2 (Data Feeder) chưa chạy | OK nếu test offline |

---

## 7. Dependencies (cần cài)

```bash
pip install redis python-dotenv sqlalchemy pyodbc pandas
```

Hoặc dùng `docs/requirements.txt`:
```bash
pip install -r docs/requirements.txt
```

---

## 8. Bước Tiếp Theo

Sau khi module Connection hoạt động OK, tiếp tục implement:

```
Module 2 (tiếp theo) → src/utils/logger.py
                      → src/utils/helpers.py

Module 3 (sau đó)   → src/core/strategy_engine.py
                      → src/strategies/strategy_comboATR.py (implement logic thực)
```
