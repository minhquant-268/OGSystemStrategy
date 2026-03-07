"""
db_connect.py
=============
Module kết nối SQL Server — cung cấp engine và hàm truy vấn dữ liệu nến lịch sử.

Trách nhiệm:
  - Đọc config từ .env (DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, DB_DRIVER)
  - Hỗ trợ cả Windows Auth (Trusted Connection) lẫn SQL Auth (UID/PWD)
  - Cung cấp sync engine (pyodbc) cho các tác vụ đồng bộ
  - Cung cấp async engine (aioodbc + SQLAlchemy) cho các tác vụ bất đồng bộ
  - Cung cấp hàm get_candles() — truy vấn lịch sử nến về dạng DataFrame chuẩn

Database Schema (tham chiếu):
  - tvc.{timeframe}  : Bảng chứa OHLCV theo timeframe (m5, m10, m15, h1, ...)
  - dbo.assets       : Lookup asset_id theo (symbol, provider)
  - dbo.timeframe    : Lookup timeframe_id theo timeframe_type
  - dbo.providers    : Lookup provider_id theo provider_code

DataFrame trả về gồm các cột:
  date_time, close_time, provider, symbol, timeframe,
  open, high, low, close, volume

Được dùng bởi:
  - back_fill_og.py  (lấy 1000 nến gần nhất cho backfill)
"""

import os
import logging
import traceback
from urllib.parse import quote_plus
from typing import Optional

import pandas as pd
import pyodbc
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Config đọc từ .env
# ─────────────────────────────────────────────
DB_SERVER   = os.getenv("DB_SERVER")
DB_NAME     = os.getenv("DB_NAME")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_DRIVER   = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

# ─────────────────────────────────────────────
# Build connection string
# ─────────────────────────────────────────────
if DB_USER and DB_PASSWORD:
    # SQL Server Authentication (UID / PWD)
    _connection_string = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};PWD={DB_PASSWORD};"
        "Encrypt=no;"
    )
else:
    # Windows Authentication (Trusted Connection)
    _connection_string = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        "Trusted_Connection=yes;Encrypt=no;"
    )

_SQLALCHEMY_URL = f"mssql+pyodbc:///?odbc_connect={quote_plus(_connection_string)}"

# ─────────────────────────────────────────────
# SQLAlchemy Sync Engine (dùng cho pandas read_sql)
# ─────────────────────────────────────────────
try:
    engine = create_engine(
        _SQLALCHEMY_URL,
        echo=False,
        pool_pre_ping=True,         # Tự kiểm tra connection trước khi dùng
        pool_size=5,
        max_overflow=10,
        connect_args={
            "timeout": 30,
            "fast_executemany": True,
        },
    )
    logger.info("[DB] SQLAlchemy engine khởi tạo thành công")
except Exception as e:
    engine = None
    logger.error(f"[DB] Không thể khởi tạo SQLAlchemy engine — {e}")


# ─────────────────────────────────────────────
# Core query functions
# ─────────────────────────────────────────────

def test_connection() -> bool:
    """
    Kiểm tra kết nối tới SQL Server.
    Dùng pyodbc trực tiếp (nhanh, không cần SQLAlchemy).

    Returns:
        True nếu kết nối OK, False nếu thất bại
    """
    try:
        with pyodbc.connect(_connection_string, timeout=5) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()[0]
            logger.info(f"[DB] Kết nối thành công — SQL Server version: {version[:50]}...")
            return True
    except Exception as e:
        logger.error(f"[DB] Kết nối thất bại — {e}")
        return False


def get_candles(
    symbol: str,
    timeframe: str,
    provider: str = "CAPITALCOM",
    limit: int = 1000,
) -> pd.DataFrame:
    """
    Lấy dữ liệu nến lịch sử từ SQL Server.

    Args:
        symbol    : Mã tài sản, vd "BTCUSD", "EURUSD"
        timeframe : Khung thời gian, vd "m10", "m15", "h1"
        provider  : Provider code, vd "CAPITALCOM", "BINANCE"
        limit     : Số nến tối đa cần lấy (mặc định 1000 nến gần nhất)

    Returns:
        pd.DataFrame với các cột:
        [date_time, close_time, provider, symbol, timeframe,
         open, high, low, close, volume]
        Được sort theo date_time tăng dần.
        Trả về DataFrame rỗng nếu không có dữ liệu hoặc lỗi.
    """
    if engine is None:
        logger.error("[DB] Engine chưa khởi tạo, không thể query")
        return _empty_candle_df()

    table_name = f"tvc.{timeframe.lower()}"
    query = text(f"""
        SELECT TOP(:limit)
            date_time,
            [open],
            [high],
            [low],
            [close],
            [volume]
        FROM {table_name}
        WHERE
            asset_id = (
                SELECT asset_id FROM dbo.assets
                WHERE symbol = :symbol AND provider = :provider
            )
            AND timeframe_id = (
                SELECT timeframe_id FROM dbo.timeframe
                WHERE timeframe_type = :timeframe
            )
            AND provider_id = (
                SELECT provider_id FROM dbo.providers
                WHERE provider_code = :provider
            )
        ORDER BY date_time DESC
    """)

    params = {
        "symbol": symbol,
        "provider": provider,
        "timeframe": timeframe,
        "limit": limit,
    }

    try:
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params=params)

        if df.empty:
            logger.warning(f"[DB] Không có dữ liệu — symbol={symbol}, tf={timeframe}, provider={provider}")
            return _empty_candle_df()

        # Sort tăng dần (DESC từ DB → reverse lại)
        df = df.sort_values("date_time").reset_index(drop=True)

        # Tính close_time: close_time[i] = date_time[i+1]
        df["close_time"] = df["date_time"].shift(-1)
        td = _timeframe_to_timedelta(timeframe)
        if td is not None and not df.empty:
            df.at[df.index[-1], "close_time"] = df["date_time"].iloc[-1] + td

        # Thêm metadata columns
        df["provider"]  = provider
        df["symbol"]    = symbol
        df["timeframe"] = timeframe

        # Chuẩn hóa kiểu dữ liệu
        df["date_time"]  = pd.to_datetime(df["date_time"])
        df["close_time"] = pd.to_datetime(df["close_time"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Sắp xếp cột theo thứ tự chuẩn
        df = df[[
            "date_time", "close_time", "provider", "symbol", "timeframe",
            "open", "high", "low", "close", "volume"
        ]]

        logger.info(f"[DB] Đã lấy {len(df)} nến — symbol={symbol}, tf={timeframe}, provider={provider}")
        return df

    except Exception as e:
        logger.error(f"[DB] Lỗi query — symbol={symbol}, tf={timeframe}: {e}")
        logger.debug(traceback.format_exc())
        return _empty_candle_df()


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _empty_candle_df() -> pd.DataFrame:
    """Trả về DataFrame rỗng với schema chuẩn."""
    return pd.DataFrame(columns=[
        "date_time", "close_time", "provider", "symbol", "timeframe",
        "open", "high", "low", "close", "volume"
    ])


def _timeframe_to_timedelta(tf: str) -> Optional[pd.Timedelta]:
    """
    Chuyển timeframe string sang pd.Timedelta để tính close_time của nến cuối.
    Hỗ trợ: m1, m5, m10, m15, m30, h1, h4, d, w
    """
    if not isinstance(tf, str) or not tf:
        return None
    t = tf.lower().strip()
    try:
        if t.startswith("m"):
            return pd.Timedelta(minutes=int(t[1:]))
        if t.startswith("h"):
            return pd.Timedelta(hours=int(t[1:]))
        if t in ("d", "d1", "day"):
            return pd.Timedelta(days=1)
        if t in ("w", "w1", "week"):
            return pd.Timedelta(weeks=1)
    except (ValueError, TypeError):
        pass
    return None
