"""
strategy_MAcrossover.py
========================
MA Crossover Strategy — Tim tin hieu vao lenh dua tren giao cat 2 EMA.

Logic chinh:
    BUY  (signal=1) khi EMA_short cat len tren EMA_long (golden cross)
    SELL (signal=2) khi EMA_short cat xuong duoi EMA_long (death cross)

Cac cot them vao DataFrame:
    MA_Short : EMA ngan han
    MA_Long  : EMA dai han
    ATR      : Average True Range (cho SL/TP)
    signal   : 0=hold, 1=buy, 2=sell
    entry    : Gia vao lenh
    sl       : Stop Loss price
    tp       : Take Profit price
    sl_distance : Khoang cach SL (pips)
    tp_distance : Khoang cach TP (pips)

Tham so:
    short_period : Chu ky EMA ngan (mac dinh 10)
    long_period  : Chu ky EMA dai (mac dinh 30)
    atr_period   : Chu ky ATR cho SL/TP (mac dinh 5)
    kSL          : He so nhan ATR cho SL (mac dinh 2.0)
    kTP          : He so nhan ATR cho TP (mac dinh 4.0)
"""

import logging
import pandas as pd
import numpy as np

from src.strategies.base_strategy import BaseStrategy
from src.indicators.MA import calculate_ema
from src.indicators.ATR import calculate_atr

logger = logging.getLogger(__name__)


class MACrossoverStrategy(BaseStrategy):

    def __init__(
        self,
        short_period: int = 10,
        long_period: int = 30,
        atr_period: int = 5,
        kSL: float = 2.0,
        kTP: float = 4.0,
    ):
        super().__init__(name="MACrossover")
        self.short_period = short_period
        self.long_period  = long_period
        self.atr_period   = atr_period
        self.kSL          = kSL
        self.kTP          = kTP

    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Tinh toan tin hieu MA Crossover tren DataFrame nen.

        Returns:
            df voi cac cot bo sung: MA_Short, MA_Long, ATR, signal,
            entry, sl, tp, sl_distance, tp_distance
        """
        try:
            if not self.validate_df(df, required_cols=["open", "high", "low", "close"]):
                return df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)

            df = df.copy()

            close = df["close"].astype(float)
            high  = df["high"].astype(float)
            low   = df["low"].astype(float)

            # ── Tinh Indicators ──────────────────────────────────────────
            df["MA_Short"] = calculate_ema(close, self.short_period)
            df["MA_Long"]  = calculate_ema(close, self.long_period)
            df["ATR"]      = calculate_atr(high, low, close, period=self.atr_period)

            # ── Dieu kien Crossover ──────────────────────────────────────
            # Golden cross: MA_Short cat len tren MA_Long
            buy_cond = (
                (df["MA_Short"].shift(1) <= df["MA_Long"].shift(1))
                & (df["MA_Short"] > df["MA_Long"])
            )
            # Death cross: MA_Short cat xuong duoi MA_Long
            sell_cond = (
                (df["MA_Short"].shift(1) >= df["MA_Long"].shift(1))
                & (df["MA_Short"] < df["MA_Long"])
            )

            # ── Sinh Signal ──────────────────────────────────────────────
            df["signal"]      = 0
            df["entry"]       = np.nan
            df["sl"]          = np.nan
            df["tp"]          = np.nan
            df["sl_distance"] = np.nan
            df["tp_distance"] = np.nan

            valid_df = df[["MA_Short", "MA_Long", "ATR"]].dropna()
            if valid_df.empty:
                logger.warning(
                    f"[{self.name}] Khong co nen nao co du indicator "
                    f"(can it nhat {self.long_period} nen)"
                )
                return df

            first_valid_idx = valid_df.index[0]

            # Vi the ban dau (khong phat sinh signal)
            row0 = df.loc[first_valid_idx]
            if row0["MA_Short"] > row0["MA_Long"]:
                current_position = 1   # LONG
            elif row0["MA_Short"] < row0["MA_Long"]:
                current_position = 2   # SHORT
            else:
                current_position = 0   # Trung tinh

            # Vong lap tu nen tiep theo
            start_i = df.index.get_loc(first_valid_idx) + 1
            for i in range(start_i, len(df)):
                row = df.iloc[i]
                if pd.isna(row["MA_Short"]) or pd.isna(row["ATR"]):
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
                "ma_short": _to_records("MA_Short"),
                "ma_long" : _to_records("MA_Long"),
                "atr"     : _to_records("ATR"),
                "signals" : _to_records("signal"),
            }
        except Exception as e:
            logger.error(f"[{self.name}] Loi get_indicators: {e}", exc_info=True)
            return {}
