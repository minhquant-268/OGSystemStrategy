"""
strategy_comboATR.py
====================
ComboATR Strategy — Tim tin hieu vao lenh dua tren MACD + SMA + ATR.

Luu y thiet ke (Cach A):
    Strategy nay KHONG tu loc symbol hay timeframe.
    Viec loc du lieu (symbol, timeframe) la trach nhiem cua strategy_engine:
        strategy_engine doc config/strategy_list.json
        -> loc df theo (provider, symbol, timeframe)
        -> goi calculate_signals(df) voi df sach cua dung 1 cap (symbol, tf)

    Strategy chi tap trung vao tinh toan indicator va sinh tin hieu.

Logic chinh:
    BUY  (signal=1) khi:
        - Nen tang (close > open)
        - Gia tren SMA (close > SMA)
        - MACD duong (MACD > 0)

    SELL (signal=2) khi:
        - Nen giam (close < open)
        - Gia duoi SMA (close < SMA)
        - MACD am (MACD < 0)

Cac cot them vao DataFrame:
    MACD, MACD_Signal, MACD_Hist : MACD indicators
    SMA                           : Simple Moving Average
    ATR                           : Average True Range (cho SL/TP)
    signal                        : 0=hold, 1=buy, 2=sell
    entry                         : Gia vao lenh
    sl                            : Stop Loss price
    tp                            : Take Profit price
    sl_distance                   : Khoang cach SL (pips)
    tp_distance                   : Khoang cach TP (pips)

Tham so:
    macd_fast   : Chu ky EMA nhanh MACD (mac dinh 5)
    macd_slow   : Chu ky EMA cham MACD (mac dinh 25)
    macd_signal : Chu ky signal line (mac dinh 5)
    sma_period  : Chu ky SMA filter (mac dinh 20)
    atr_period  : Chu ky ATR cho SL/TP (mac dinh 5)
    kSL         : He so nhan ATR cho SL (mac dinh 2.3)
    kTP         : He so nhan ATR cho TP (mac dinh 5.3)
"""

import logging
import pandas as pd
import numpy as np

from src.strategies.base_strategy import BaseStrategy
from src.utils.indicators.MACD import calculate_macd
from src.utils.indicators.MA import calculate_sma
from src.utils.indicators.ATR import calculate_atr

logger = logging.getLogger(__name__)


class ComboATRStrategy(BaseStrategy):

    def __init__(
        self,
        macd_fast: int = 2, #5
        macd_slow: int = 10, #25
        macd_signal: int = 5, #5
        sma_period: int = 20, #20
        atr_period: int = 5, #5
        kSL: float = 2.3, #2.3
        kTP: float = 5.3,
    ):
        super().__init__(name="ComboATR")
        self.macd_fast   = macd_fast
        self.macd_slow   = macd_slow
        self.macd_signal = macd_signal
        self.sma_period  = sma_period
        self.atr_period  = atr_period
        self.kSL         = kSL
        self.kTP         = kTP

    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Tinh toan tin hieu ComboATR tren DataFrame nen.

        Nhan vao df cua DUNG MOT cap (symbol, timeframe) — viec loc nay
        do strategy_engine thuc hien truoc khi goi ham nay.
        Xem: src/core/strategy_engine.py

        Args:
            df : pd.DataFrame voi cac cot bat buoc:
                 [date_time, open, high, low, close]
                 Sap xep theo date_time tang dan.

        Returns:
            df voi cac cot bo sung: MACD, SMA, ATR, signal, entry, sl, tp,
            sl_distance, tp_distance
        """
        try:
            if not self.validate_df(df, required_cols=["open", "high", "low", "close"]):
                return df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)

            df = df.copy()

            close  = df["close"].astype(float)
            high   = df["high"].astype(float)
            low    = df["low"].astype(float)
            open_  = df["open"].astype(float)

            # ── Tinh Indicators ──────────────────────────────────────────
            df["MACD"], df["MACD_Signal"], df["MACD_Hist"] = calculate_macd(
                close,
                fast_period=self.macd_fast,
                slow_period=self.macd_slow,
                signal_period=self.macd_signal,
            )
            df["SMA"] = calculate_sma(close, period=self.sma_period)
            df["ATR"] = calculate_atr(high, low, close, period=self.atr_period)

            # ── Dieu kien vao lenh ───────────────────────────────────────
            buy_cond = (
                (close > open_)         # Nen tang
                & (close > df["SMA"])   # Gia tren SMA
                & (df["MACD"] > 0)      # MACD duong
            )
            sell_cond = (
                (close < open_)         # Nen giam
                & (close < df["SMA"])   # Gia duoi SMA
                & (df["MACD"] < 0)      # MACD am
            )

            # ── Sinh Signal (trang thai hien tai, khong repeat) ──────────
            df["signal"]      = 0
            df["entry"]       = np.nan
            df["sl"]          = np.nan
            df["tp"]          = np.nan
            df["sl_distance"] = np.nan
            df["tp_distance"] = np.nan

            # Tim nen dau tien co du du lieu indicator
            valid_df = df[["MACD", "SMA", "ATR"]].dropna()
            if valid_df.empty:
                logger.warning(f"[{self.name}] Khong co nen nao co du indicator (can it nhat {self.macd_slow} nen)")
                return df

            first_valid_idx = valid_df.index[0]

            # Xac dinh vi the ban dau (khong phat sinh signal)
            row0 = df.loc[first_valid_idx]
            if (row0["close"] > row0["open"]
                    and row0["close"] > row0["SMA"]
                    and row0["MACD"] > 0):
                current_position = 1   # Dang LONG
            else:
                current_position = 2   # Dang SHORT / neutral

            # Vong lap tu nen tiep theo
            start_i = df.index.get_loc(first_valid_idx) + 1
            for i in range(start_i, len(df)):
                row = df.iloc[i]
                if pd.isna(row["MACD"]) or pd.isna(row["ATR"]):
                    continue

                idx     = df.index[i]
                atr_val = row["ATR"]
                close_i = row["close"]

                if buy_cond.iloc[i] and current_position != 1:
                    df.loc[idx, "signal"]      = 1
                    df.loc[idx, "entry"]       = close_i
                    df.loc[idx, "sl_distance"] = round(self.kSL * atr_val, 5)
                    df.loc[idx, "tp_distance"] = round(self.kTP * atr_val, 5)
                    df.loc[idx, "sl"]          = round(close_i - self.kSL * atr_val, 5)
                    df.loc[idx, "tp"]          = round(close_i + self.kTP * atr_val, 5)
                    current_position = 1

                elif sell_cond.iloc[i] and current_position != 2:
                    df.loc[idx, "signal"]      = 2
                    df.loc[idx, "entry"]       = close_i
                    df.loc[idx, "sl_distance"] = round(self.kSL * atr_val, 5)
                    df.loc[idx, "tp_distance"] = round(self.kTP * atr_val, 5)
                    df.loc[idx, "sl"]          = round(close_i + self.kSL * atr_val, 5)
                    df.loc[idx, "tp"]          = round(close_i - self.kTP * atr_val, 5)
                    current_position = 2

            signals_count = (df["signal"] != 0).sum()
            logger.info(
                f"[{self.name}] Hoan thanh | {len(df)} nen | "
                f"{signals_count} tin hieu | "
                f"BUY={(df['signal']==1).sum()} SELL={(df['signal']==2).sum()}"
            )
            return df

        except Exception as e:
            logger.error(f"[{self.name}] Loi calculate_signals: {e}", exc_info=True)
            return df

    def get_indicators(self, df: pd.DataFrame) -> dict:
        """Tra ve dict indicator de chart/debug."""
        try:
            if not isinstance(df, pd.DataFrame) or df.empty:
                return {}

            def _to_records(col):
                if col in df.columns and "date_time" in df.columns:
                    return (
                        df[["date_time", col]]
                        .rename(columns={"date_time": "time", col: "value"})
                        .dropna()
                        .to_dict("records")
                    )
                return []

            return {
                "macd"        : _to_records("MACD"),
                "macd_signal" : _to_records("MACD_Signal"),
                "macd_hist"   : _to_records("MACD_Hist"),
                "sma"         : _to_records("SMA"),
                "atr"         : _to_records("ATR"),
                "signals"     : _to_records("signal"),
            }
        except Exception as e:
            logger.error(f"[{self.name}] Loi get_indicators: {e}", exc_info=True)
            return {}
