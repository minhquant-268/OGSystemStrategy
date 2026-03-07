"""
redis_connect.py
================
Module kết nối Redis — cung cấp Redis client để toàn bộ hệ thống dùng chung.

Trách nhiệm:
  - Đọc config từ .env (REDIS_HOST, REDIS_PORT, REDIS_PASSWORD)
  - Cung cấp singleton client (dùng lại kết nối, auto-reconnect nếu mất)
  - Cung cấp factory client (dùng khi cần kết nối tới DB index khác, vd DB0 vs DB1)
  - Cung cấp các hàm Redis thường dùng trong hệ thống:
      + get_candle_bucket()   : Lấy tất cả nến từ bucket pattern candle:*
      + hset_hash()           : Ghi 1 hash key lên Redis
      + lpush_list()          : Thêm item vào list key
      + publish_channel()     : Publish message lên pub/sub channel
      + scan_keys()           : Scan key pattern an toàn (thay cho KEYS)

Được dùng bởi:
  - src/core/keyspace_monitor.py  (subscribe keyspace, đọc candle bucket)
  - src/core/redis_publisher.py   (ghi OG hash, signal hash, publish channel)
  - src/core/cleanup_worker.py    (scan + delete old keys)
  - back_fill_og.py               (đọc dữ liệu để backfill)
"""

import os
import redis
import logging
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Config đọc từ .env
# ─────────────────────────────────────────────
_BASE_CONFIG: Dict[str, Any] = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "password": os.getenv("REDIS_PASSWORD") or None,
    "decode_responses": True,          # Auto decode bytes -> str
    "socket_connect_timeout": 5,       # Timeout kết nối ban đầu (giây)
    "socket_timeout": 10,              # Timeout mỗi lệnh Redis (giây)
    "health_check_interval": 30,       # Tự ping để giữ connection sống
    "retry_on_timeout": True,
}

# ─────────────────────────────────────────────
# Singleton client (dùng chung cho DB=0)
# ─────────────────────────────────────────────
_singleton_client: Optional[redis.Redis] = None


def create_redis_client(db: int = 0, extra_opts: Optional[Dict[str, Any]] = None) -> Optional[redis.Redis]:
    """
    Tạo Redis client mới với DB index chỉ định.
    Dùng khi cần client riêng (ví dụ cleanup_worker cần client tách biệt).

    Args:
        db          : Redis DB index (0 = mặc định toàn hệ thống)
        extra_opts  : Tuỳ chọn bổ sung ghi đè config mặc định

    Returns:
        redis.Redis instance nếu kết nối thành công, None nếu thất bại
    """
    conf = {**_BASE_CONFIG, "db": db}
    if extra_opts:
        conf.update(extra_opts)

    try:
        client = redis.Redis(**conf)
        client.ping()
        logger.info(f"[Redis] Kết nối thành công — host={conf['host']}, port={conf['port']}, db={db}")
        return client
    except redis.exceptions.ConnectionError as e:
        logger.error(f"[Redis] Không thể kết nối — {e}")
        return None
    except Exception as e:
        logger.error(f"[Redis] Lỗi không xác định khi kết nối — {e}")
        return None


def get_redis_client(db: int = 0) -> Optional[redis.Redis]:
    """
    Lấy singleton Redis client (DB=0 mặc định).
    Kiểm tra và tự động reconnect nếu kết nối bị mất.

    Returns:
        redis.Redis instance nếu kết nối OK, None nếu không thể kết nối
    """
    global _singleton_client

    if _singleton_client is not None:
        try:
            _singleton_client.ping()
            return _singleton_client
        except Exception:
            logger.warning("[Redis] Singleton client mất kết nối, đang reconnect...")
            try:
                _singleton_client.close()
            except Exception:
                pass
            _singleton_client = None

    _singleton_client = create_redis_client(db=db)
    return _singleton_client


def close_redis_client() -> None:
    """Đóng singleton client — gọi khi shutdown hệ thống."""
    global _singleton_client
    if _singleton_client:
        try:
            _singleton_client.close()
            logger.info("[Redis] Đã đóng singleton client")
        except Exception as e:
            logger.error(f"[Redis] Lỗi khi đóng client — {e}")
        finally:
            _singleton_client = None


# ─────────────────────────────────────────────
# Helper functions dùng chung
# ─────────────────────────────────────────────

def scan_keys(client: redis.Redis, pattern: str, key_type: Optional[str] = None) -> List[str]:
    """
    Scan tất cả key khớp pattern — an toàn hơn KEYS (không block Redis).

    Args:
        client   : Redis client
        pattern  : Glob pattern, vd "candle:CAPITALCOM:BTCUSD:15:*"
        key_type : Lọc theo loại key ("hash", "list", "string", ...) — None = tất cả

    Returns:
        List[str] các key tìm được
    """
    keys = []
    cursor = 0
    try:
        while True:
            scan_kwargs = {"cursor": cursor, "match": pattern, "count": 500}
            if key_type:
                scan_kwargs["_type"] = key_type
            cursor, batch = client.scan(**scan_kwargs)
            keys.extend(batch)
            if cursor == 0:
                break
    except Exception as e:
        logger.error(f"[Redis] scan_keys lỗi — pattern={pattern}: {e}")
    return keys


def get_candle_bucket(
    client: redis.Redis,
    provider: str,
    symbol: str,
    timeframe: str
) -> List[Dict[str, str]]:
    """
    Lấy toàn bộ nến trong bucket: candle:{provider}:{symbol}:{timeframe}:*
    Mỗi nến là 1 Hash trên Redis.

    Args:
        client     : Redis client
        provider   : Provider code, vd "CAPITALCOM"
        symbol     : Symbol code, vd "BTCUSD"
        timeframe  : Timeframe (minute string), vd "15"

    Returns:
        List of dict — mỗi dict là 1 nến (tất cả field đã decode sang str)
        Bao gồm field "_key" để biết Redis key gốc.
    """
    pattern = f"candle:{provider}:{symbol}:{timeframe}:*"
    keys = scan_keys(client, pattern, key_type="hash")

    if not keys:
        logger.warning(f"[Redis] Không tìm thấy nến nào — bucket={pattern}")
        return []

    records = []
    for key in keys:
        try:
            raw = client.hgetall(key)
            if raw:
                record = {k: v for k, v in raw.items()}
                record["_key"] = key            # giữ lại key gốc
                records.append(record)
        except Exception as e:
            logger.error(f"[Redis] hgetall lỗi — key={key}: {e}")

    logger.debug(f"[Redis] Đọc được {len(records)} nến từ bucket {pattern}")
    return records


def hset_hash(client: redis.Redis, key: str, mapping: Dict[str, Any]) -> bool:
    """
    Ghi 1 Hash key lên Redis.

    Args:
        client  : Redis client
        key     : Key đích
        mapping : Dict các field:value cần ghi

    Returns:
        True nếu thành công, False nếu lỗi
    """
    try:
        # Convert tất cả value sang str để tránh type error
        safe_mapping = {k: str(v) for k, v in mapping.items()}
        client.hset(key, mapping=safe_mapping)
        return True
    except Exception as e:
        logger.error(f"[Redis] hset_hash lỗi — key={key}: {e}")
        return False


def lpush_list(client: redis.Redis, list_key: str, value: str) -> bool:
    """
    Thêm value vào đầu list key.

    Args:
        client   : Redis client
        list_key : List key đích
        value    : Giá trị cần push (thường là datetime string)

    Returns:
        True nếu thành công
    """
    try:
        client.lpush(list_key, value)
        return True
    except Exception as e:
        logger.error(f"[Redis] lpush_list lỗi — key={list_key}: {e}")
        return False


def publish_channel(client: redis.Redis, channel: str, message: str) -> bool:
    """
    Publish message lên pub/sub channel.

    Args:
        client  : Redis client
        channel : Channel name
        message : Message string (thường là JSON)

    Returns:
        True nếu thành công
    """
    try:
        client.publish(channel, message)
        return True
    except Exception as e:
        logger.error(f"[Redis] publish_channel lỗi — channel={channel}: {e}")
        return False


def enable_keyspace_notifications(client: redis.Redis, events: str = "KEA") -> bool:
    """
    Bật Redis Keyspace Notification.
    Cần gọi 1 lần khi khởi động keyspace_monitor.

    Args:
        client : Redis client
        events : Loại event cần bật (mặc định KEA = Keyspace + All events)

    Returns:
        True nếu thành công
    """
    try:
        client.config_set("notify-keyspace-events", events)
        logger.info(f"[Redis] Đã bật keyspace notifications — events={events}")
        return True
    except Exception as e:
        logger.error(f"[Redis] Không thể bật keyspace notifications — {e}")
        return False
