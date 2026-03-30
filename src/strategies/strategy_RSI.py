"""
strategy_RSI.py
===============
RSI Strategy — Tim tin hieu vao lenh dua tren nguong qua mua / qua ban cua RSI.

Logic chinh:
    BUY  (signal=1) khi RSI < nguong oversold (mac dinh 30)
    SELL (signal=2) khi RSI > nguong overbought (mac dinh 70)

Dac diem:
    - Don gian, phu hop lam strategy bo sung hoac test nhanh
    - Tin hieu xuat hien khi RSI DANG trong vung qua mua/qua ban (khong can crossover)
    - Tranh tin hieu lap: chi doi lenh khi vi the thay doi

Cac cot them vao DataFrame:
    RSI      : RSI indicator
    signal   : 0=hold, 1=buy, 2=sell
    entry    : Gia vao lenh
    sl, tp   : Stop Loss / Take Profit
    sl_distance, tp_distance : Khoang cach SL/TP (pips)

Tham so:
    rsi_period   : Chu ky tinh RSI (mac dinh 14)
    overbought   : Nguong qua mua (mac dinh 70)
    oversold     : Nguong qua ban (mac dinh 30)
    atr_period   : Chu ky ATR cho SL/TP (mac dinh 5)
    kSL          : He so nhan ATR cho SL (mac dinh 1.5)
    kTP          : He so nhan ATR cho TP (mac dinh 3.0)
"""

import logging
import pandas as pd
import numpy as np

from src.strategies.base_strategy import BaseStrategy
from src.indicators.RSI import calculate_rsi
from src.indicators.ATR import calculate_atr

logger = logging.getLogger(__name__)


class RSIStrategy(BaseStrategy):

    def __init__(
        self,
        rsi_period: int = 14,
        overbought: float = 70.0,
        oversold: float = 30.0,
        atr_period: int = 5,
        kSL: float = 1.5,
        kTP: float = 3.0,
    ):
        super().__init__(name="RSIStrategy")
        self.rsi_period  = rsi_period
        self.overbought  = overbought
        self.oversold    = oversold
        self.atr_period  = atr_period
        self.kSL         = kSL
        self.kTP         = kTP

    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Tinh toan tin hieu RSI tren DataFrame nen.

        Returns:
            df voi cac cot bo sung: RSI, ATR, signal, entry, sl, tp,
            sl_distance, tp_distance
        """
        try:
            if not self.validate_df(df, required_cols=["open", "high", "low", "close"]):
                return df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)

            df = df.copy()

            close = df["close"].astype(float)
            high  = df["high"].astype(float)
            low   = df["low"].astype(float)

            # ── Tinh Indicators ──────────────────────────────────────────
            df["RSI"] = calculate_rsi(close, period=self.rsi_period)
            df["ATR"] = calculate_atr(high, low, close, period=self.atr_period)

            # ── Dieu kien vao lenh ───────────────────────────────────────
            buy_cond  = df["RSI"] < self.oversold    # RSI qua ban -> BUY
            sell_cond = df["RSI"] > self.overbought  # RSI qua mua -> SELL

            # ── Sinh Signal ──────────────────────────────────────────────
            df["signal"]      = 0
            df["entry"]       = np.nan
            df["sl"]          = np.nan
            df["tp"]          = np.nan
            df["sl_distance"] = np.nan
            df["tp_distance"] = np.nan

            valid_df = df[["RSI", "ATR"]].dropna()
            if valid_df.empty:
                logger.warning(
                    f"[{self.name}] Khong co nen nao co du indicator "
                    f"(can it nhat {self.rsi_period} nen)"
                )
                return df

            first_valid_idx = valid_df.index[0]

            # Vi the ban dau (khong phat sinh signal)
            row0 = df.loc[first_valid_idx]
            if row0["RSI"] < self.oversold:
                current_position = 1
            elif row0["RSI"] > self.overbought:
                current_position = 2
            else:
                current_position = 0

            # Vong lap tu nen tiep theo
            start_i = df.index.get_loc(first_valid_idx) + 1
            for i in range(start_i, len(df)):
                row = df.iloc[i]
                if pd.isna(row["RSI"]) or pd.isna(row["ATR"]):
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
                "rsi"    : _to_records("RSI"),
                "atr"    : _to_records("ATR"),
                "signals": _to_records("signal"),
            }
        except Exception as e:
            logger.error(f"[{self.name}] Loi get_indicators: {e}", exc_info=True)
            return {}
