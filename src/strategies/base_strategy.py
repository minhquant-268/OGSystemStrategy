"""
base_strategy.py
================
Abstract base class cho tat ca strategy trong he thong.

Moi strategy PHAI ke thua BaseStrategy va implement:
    - calculate_signals(df) : tính toán tin hieu BUY/SELL tren DataFrame nen
    - get_indicators(df)    : (tuy chon) tra ve dict indicator de chart/debug

Quy uoc signal:
    0 = Khong co tin hieu (HOLD)
    1 = BUY signal
    2 = SELL signal
"""

import logging
import pandas as pd
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """
    Abstract base class cho tat ca trading strategy.

    Subclass bat buoc override:
        calculate_signals(df: pd.DataFrame) -> pd.DataFrame

    Subclass co the override:
        get_indicators(df: pd.DataFrame) -> dict
    """

    def __init__(self, name: str = "BaseStrategy"):
        self.name = name

    @abstractmethod
    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Tinh toan tin hieu giao dich tren DataFrame nen.

        Args:
            df : pd.DataFrame voi cac cot bat buoc:
                 [date_time, open, high, low, close, volume]
                 Thong thuong cung co: [provider, symbol, timeframe, close_time]

        Returns:
            pd.DataFrame goc duoc bo sung them cac cot:
                signal       : int (0=hold, 1=buy, 2=sell)
                [entry, sl, tp, sl_distance, tp_distance] : float (neu co tinh)
                [MACD, SMA, ATR, RSI, ...]                : cac cot indicator

            QUAN TRONG:
                - Luon tra ve df (ke ca khi loi) - khong raise exception ra ngoai
                - Moi strategy tu quan ly exception cua chinh no
                - Khong modify df goc, dung df.copy() truoc khi xu ly
        """
        raise NotImplementedError(f"Strategy '{self.name}' chua implement calculate_signals()")

    def get_indicators(self, df: pd.DataFrame) -> dict:
        """
        (Tuy chon) Tra ve dict cac indicator de hien thi tren chart hoac debug.

        Returns:
            dict voi key la ten indicator, value la list of dicts:
            {
                "macd":   [{"time": "2026-03-07T22:00:00", "value": 0.23}, ...],
                "signal": [{"time": "2026-03-07T22:00:00", "value": 1}, ...],
            }
            Tra ve {} neu khong co indicator nao can return.
        """
        return {}

    def validate_df(self, df: pd.DataFrame, required_cols: list = None) -> bool:
        """
        Kiem tra DataFrame co hop le truoc khi tinh toan.
        Subclass co the goi ham nay o dau calculate_signals().

        Args:
            df            : DataFrame can kiem tra
            required_cols : Danh sach cot bat buoc (mac dinh: open, high, low, close)

        Returns:
            True neu hop le, False neu co van de.
        """
        if required_cols is None:
            required_cols = ["open", "high", "low", "close"]

        if not isinstance(df, pd.DataFrame):
            logger.warning(f"[{self.name}] Input khong phai DataFrame")
            return False
        if df.empty:
            logger.warning(f"[{self.name}] DataFrame rong")
            return False

        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            logger.warning(f"[{self.name}] Thieu cot: {missing}")
            return False

        return True

    def __repr__(self) -> str:
        return f"<Strategy: {self.name}>"
