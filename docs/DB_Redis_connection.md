# Module Connection — Tài Liệu Triển Khai

> **Module**: Connection Layer
> **Vị trí**: `src/utils/connection/`
> **Ngày cập nhật**: 2026-03-07
> **Trạng thái**: ✅ Hoàn thành — Đã test thực tế PASS

---

## 1. Tổng Quan

Module Connection là **tầng hạ tầng (infrastructure layer)** — đóng gói toàn bộ logic kết nối tới SQL Server và Redis. Các module bên trên (`core/`, `strategies/`) **không bao giờ gọi thẳng pyodbc hay redis-py** mà chỉ gọi qua các hàm trong module này.

```
Các module bên trên                    Module Connection
──────────────────────────────────     ────────────────────────────────────
src/core/keyspace_monitor.py      →    redis_connect.get_redis_client()
                                        redis_connect.get_candle_bucket()
                                        redis_connect.enable_keyspace_notifications()
src/core/redis_publisher.py       →    redis_connect.hset_hash()
                                        redis_connect.lpush_list()
                                        redis_connect.publish_channel()
src/core/cleanup_worker.py        →    redis_connect.scan_keys()
                                        redis_connect.create_redis_client()
back_fill_og.py                   →    db_connect.get_candles()
                                        redis_connect.hset_hash()
                                        redis_connect.lpush_list()
```

---

## 2. Files

| File | Vai trò |
|---|---|
| `src/utils/connection/db_connect.py` | Kết nối SQL Server — engine khởi tạo lúc import, cung cấp `get_candles()` |
| `src/utils/connection/redis_connect.py` | Kết nối Redis — singleton client, auto-reconnect, helper functions |
| `.env` | Biến môi trường — host, port, credentials (không push Git) |
| `tests/test_connection.py` | Manual test: query DB → push lên Redis → verify trên Redis Desktop |

---

## 3. Cấu Hình (.env)

```env
# SQL Server Authentication
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

> [!IMPORTANT]
> **Cả hai module đều fail-fast nếu thiếu biến môi trường bắt buộc:**
> - `redis_connect.py` raise `EnvironmentError` ngay khi import nếu `REDIS_HOST` chưa set
> - `db_connect.py` set `engine = None` và log lỗi rõ ràng nếu `DB_SERVER` hoặc `DB_NAME` chưa set

> [!CAUTION]
> File `.env` chứa credentials thật — đã thêm vào `.gitignore`, không được push lên Git.

---

## 4. SQL DB (`db_connect.py`)

### 4.1 Khởi tạo Engine

Engine được tạo **tự động khi import module** (module-level singleton):

```python
# Tự động khi import:
# - Đọc DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, DB_DRIVER từ .env
# - Build connection string (SQL Auth hoặc Windows Trusted Connection)
# - Khởi tạo SQLAlchemy engine với pool_size=5, pool_pre_ping=True
# - Nếu DB_SERVER hoặc DB_NAME chưa set -> engine = None (không crash)
```

Hỗ trợ **2 chế độ xác thực**:
- **SQL Authentication**: khi có `DB_USER` và `DB_PASSWORD` → dùng `UID/PWD`
- **Windows Authentication**: khi thiếu user/pass → dùng `Trusted_Connection=yes`

### 4.2 Hàm chính

```python
from src.utils.connection.db_connect import test_connection, get_candles, engine

# Kiểm tra kết nối (dùng pyodbc trực tiếp, nhanh)
ok = test_connection()  # True / False

# Lấy dữ liệu nến lịch sử
# provider là REQUIRED — không có default, phải truyền tường minh
df = get_candles(
    symbol="US30",          # Mã tài sản
    timeframe="m10",        # Phải match tên bảng: tvc.m10
    provider="CAPITALCOM",  # Required — lấy từ DB hoặc strategy_list.json
    limit=1000              # N nến gần nhất (ORDER BY date_time DESC LIMIT N)
)

# Truy cập engine trực tiếp nếu cần query tùy chỉnh
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text("SELECT DISTINCT provider FROM dbo.assets WHERE symbol = :s"), {"s": "US30"})
```

> [!IMPORTANT]
> `provider` trong `get_candles()` là **required argument** (không có default value).
> Caller phải truyền tường minh để tránh hardcode business logic trong tầng infrastructure.

### 4.3 DataFrame trả về

| Cột | Kiểu | Mô tả |
|---|---|---|
| `date_time` | datetime | Thời gian mở nến — sorted tăng dần |
| `close_time` | datetime | Thời gian đóng nến — tự tính = `date_time` nến tiếp theo |
| `provider` | str | Provider code truyền vào |
| `symbol` | str | Symbol code truyền vào |
| `timeframe` | str | Timeframe string truyền vào |
| `open` | float | Giá mở |
| `high` | float | Giá cao nhất |
| `low` | float | Giá thấp nhất |
| `close` | float | Giá đóng |
| `volume` | float | Khối lượng |

**Lưu ý:**
- DB trả về `ORDER BY date_time DESC` → hàm reverse lại thành tăng dần
- `close_time` của nến cuối = `date_time[-1] + timedelta(timeframe)`
- Trả về `DataFrame` rỗng (đúng schema) nếu không có dữ liệu hoặc lỗi, **không raise exception**

### 4.4 DB Schema (tham chiếu)

```sql
-- Bảng nến: tvc.m5, tvc.m10, tvc.m15, tvc.h1, ...
SELECT TOP(:limit)
    date_time, open, high, low, close, volume
FROM tvc.{timeframe}
WHERE
    asset_id    = (SELECT asset_id    FROM dbo.assets    WHERE symbol = :symbol AND provider = :provider)
    AND timeframe_id = (SELECT timeframe_id FROM dbo.timeframe WHERE timeframe_type = :timeframe)
    AND provider_id  = (SELECT provider_id  FROM dbo.providers WHERE provider_code = :provider)
ORDER BY date_time DESC
```

---

## 5. Redis (`redis_connect.py`)

### 5.1 Fail-fast khi thiếu config

```python
# redis_connect.py bắn EnvironmentError ngay khi import nếu REDIS_HOST chưa set:
# EnvironmentError: [Redis] REDIS_HOST chua duoc set trong .env
#                   Chinh sua file .env va them: REDIS_HOST=<dia_chi_redis>

# Không có fallback "localhost" — tránh connect nhầm server trong production
```

### 5.2 Client management

```python
from src.utils.connection.redis_connect import (
    get_redis_client,       # Singleton — dùng trong hầu hết trường hợp
    create_redis_client,    # Factory — khi cần client riêng biệt
    close_redis_client,     # Đóng singleton khi shutdown hệ thống
)

# Singleton client (DB=0) — có auto-reconnect nếu mất kết nối
client = get_redis_client(db=0)

# Factory client — dùng cho cleanup_worker (cần client tách biệt khỏi main thread)
worker_client = create_redis_client(db=0, extra_opts={"socket_timeout": 30})

# Shutdown
close_redis_client()
```

**Config mặc định của client:**

| Tham số | Giá trị | Mô tả |
|---|---|---|
| `decode_responses` | `True` | Auto decode bytes → str |
| `socket_connect_timeout` | `5s` | Timeout kết nối ban đầu |
| `socket_timeout` | `10s` | Timeout mỗi lệnh |
| `health_check_interval` | `30s` | Tự ping để giữ connection sống |
| `retry_on_timeout` | `True` | Tự retry khi timeout |

### 5.3 Helper functions

```python
from src.utils.connection.redis_connect import (
    scan_keys,
    get_candle_bucket,
    hset_hash,
    lpush_list,
    publish_channel,
    enable_keyspace_notifications,
)

# Scan keys an toàn (dùng SCAN thay cho KEYS — không block Redis)
keys = scan_keys(client, "OG:comboATR:*", key_type="hash")
#   key_type: "hash" | "list" | "string" | None (tất cả)

# Lấy tất cả nến trong bucket (trả về List[Dict] mỗi dict = 1 nến)
# Có thêm field "_key" trong mỗi dict để biết Redis key gốc
records = get_candle_bucket(client, provider="CAPITALCOM", symbol="US30", timeframe="m10")

# Ghi Hash key (auto convert tất cả value sang str trước khi ghi)
hset_hash(client, "OG:comboATR:CAPITALCOM:US30:m10:2026-03-07 22:00:00", payload_dict)

# Thêm vào List (index datetime)
lpush_list(client, "OG:comboATR:CAPITALCOM:US30:m10", "2026-03-07 22:00:00")

# Publish signal lên pub/sub channel
import json
publish_channel(client, "signals_channel:comboATR:CAPITALCOM:US30:m10", json.dumps(signal_dict))

# Bật keyspace notification — gọi 1 lần khi khởi động keyspace_monitor
enable_keyspace_notifications(client, events="KEA")
#   events: "KEA" = Keyspace + Expired + All commands
```

### 5.4 Redis Key Convention

| Pattern | Type Redis | Ghi bởi | Đọc bởi |
|---|---|---|---|
| `candle:{provider}:{symbol}:{tf}:{dt}` | Hash | Module 2 (Data Feeder) | `keyspace_monitor` |
| `OG:{strategy}:{provider}:{symbol}:{tf}:{dt}` | Hash | `redis_publisher` | Dashboard, OF_ctrader |
| `OG:{strategy}:{provider}:{symbol}:{tf}` | List | `redis_publisher` | Dashboard query |
| `signal:{strategy}:{provider}:{symbol}:{tf}:{dt}` | Hash | `redis_publisher` | OF_ctrader |
| `signal:{strategy}:{provider}:{symbol}:{tf}` | List | `redis_publisher` | OF_ctrader query |
| `signals_channel:{strategy}:{provider}:{symbol}:{tf}` | Pub/Sub | `redis_publisher` | OF_ctrader (subscribe) |

---

## 6. Chạy Test

```bash
cd "c:\Users\Administrator\Desktop\sen15_by_NP\system revise\system_strategy_revise"

# Chay test: query US30 tu DB -> day len Redis -> GIU LAI de xem tren Redis Desktop
python tests/test_connection.py

# Doi timeframe
python tests/test_connection.py --timeframe=m15

# Chay xong don dep tat ca test key
python tests/test_connection.py --clean
```

### Kết quả mong đợi khi PASS

```
=================================================================
  MODULE CONNECTION - DB to Redis Test
  Symbol    : US30
  Timeframe : m10
  Limit     : 10 nen
  Mode      : GIU DATA tren Redis Desktop
=================================================================

TEST 1.1 - SQL Server Connection
  [PASS] Ket noi SQL Server thanh cong

TEST 1.2 - get_candles cho tat ca provider
  [DB]  Tim thay 1 provider cho US30: ['CAPITALCOM']
  [OK]   10 nen | Tu: 2026-02-20 20:10:00 -> Den: 2026-02-20 21:40:00
  [PASS] Lay duoc du lieu tu 1 provider: ['CAPITALCOM']

TEST 2.1 - Redis Connection
  [PASS] Ket noi Redis thanh cong — Redis 6.0.16

TEST 2.2 - Day du lieu DB -> Redis
  [PASS] Da ghi 10/10 nen len Redis
  [CHECK] Tim thay 11 key tren Redis DB0
    LIST  (10 items) : test:db_to_redis:CAPITALCOM:US30:m10
    HASH  (12 fields): test:db_to_redis:CAPITALCOM:US30:m10:2026-02-20 20:10:00
    ...

  PASS: 4 | FAIL: 0 | SKIP: 1
=================================================================
```

### Dữ liệu trên Redis Desktop sau test

```
DB0
└── test:db_to_redis:*
    ├── test:db_to_redis:CAPITALCOM:US30:m10        (List — 10 items)
    └── test:db_to_redis:CAPITALCOM:US30:m10:{dt}   (Hash — 12 fields mỗi nến)
```

Mỗi Hash chứa: `date_time`, `close_time`, `provider`, `symbol`, `timeframe`, `open`, `high`, `low`, `close`, `volume`, `_source`, `_written_at`

### Xử lý khi FAIL

| Lỗi | Nguyên nhân | Cách fix |
|---|---|---|
| `EnvironmentError: REDIS_HOST` | `.env` chưa có `REDIS_HOST` | Thêm `REDIS_HOST=...` vào `.env` |
| `engine = None` | `.env` thiếu `DB_SERVER` hoặc `DB_NAME` | Thêm đủ DB config |
| DB Connection FAIL | Sai credentials hoặc server không chạy | Kiểm tra `.env` DB_* |
| DB get_candles rỗng | Bảng `tvc.m10` không có data hoặc sai symbol | Kiểm tra DB schema + symbol |
| Redis Connection FAIL | Redis server không chạy hoặc sai password | Kiểm tra `.env` REDIS_* |
| `candle:*` bucket rỗng | Module 2 (Data Feeder) chưa chạy | Bình thường khi test offline |

---

## 7. Dependencies

```bash
pip install redis python-dotenv sqlalchemy pyodbc pandas
```

Hoặc:
```bash
pip install -r docs/requirements.txt
```

---

## 8. Bước Tiếp Theo

```
Module tiep theo → src/utils/logger.py     (centralized logging)
                 → src/utils/helpers.py    (normalize_dt, timestamp_to_ms)

Module sau do   → src/core/keyspace_monitor.py  (subscribe Redis Keyspace)
                → src/core/strategy_engine.py   (load + run strategies)
```
