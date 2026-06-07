"""
signal_filter.py
================
Bo loc tin hieu — ket hop KNN Trend voi strategy signal de tao final signal.

Flow:
    1. Nhan StrategyResult (chua df_result voi cot 'signal' tu strategy)
    2. Chay calculate_knn_trend() tren DataFrame do
    3. So sanh strategy signal voi knn_prediction:
        - BUY  (1) + knn_prediction > 0 (bullish)  -> final = BUY  (1)
        - SELL (2) + knn_prediction < 0 (bearish)   -> final = SELL (2)
        - Nguoc lai                                 -> final = HOLD (0)
    4. Ghi de cot 'signal' bang final signal
    5. Them cac cot KNN indicator vao DataFrame (phuc vu debug/dashboard)

Duoc goi boi:
    - src/core/keyspace_monitor.py  (realtime)
    - back_fill_og.py               (backfill)

Thiet ke:
    - KHONG sua code ben trong cac strategy (ComboATR, MACrossover, RSI...)
    - Strategy van tao signal binh thuong
    - Signal filter chi la lop loc ben ngoai, de bat/tat
    - Neu KNN filter bi tat (enabled=False), signal goc duoc giu nguyen
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.indicators.KNN_trend import calculate_knn_trend

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Config mac dinh cho KNN filter
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_KNN_CONFIG = {
    "enabled": True,
    "price_method": "hl2",
    "target_method": "rma",
    "ma_len": 5,
    "target_ma_len": 5,
    "n_neighbors": 3,
    "smoothing_period": 50,
}


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: apply_knn_filter
# ─────────────────────────────────────────────────────────────────────────────

def apply_knn_filter(result, knn_config: Optional[dict] = None):
    """
    Ap dung KNN Trend filter len StrategyResult.

    Logic:
        - Luu signal goc tu strategy vao cot 'strategy_signal'
        - Chay KNN Trend tren (high, low, close) cua df_result
        - So sanh:
            strategy_signal == 1 (BUY)  AND knn_prediction > 0  -> final = 1 (BUY)
            strategy_signal == 2 (SELL) AND knn_prediction < 0  -> final = 2 (SELL)
            Nguoc lai                                           -> final = 0 (HOLD)
        - Ghi de cot 'signal' bang final signal
        - Neu signal bi filter bo (final=0): set entry/sl/tp/sl_distance/tp_distance = NaN

    Args:
        result     : StrategyResult tu strategy_engine
        knn_config : dict cau hinh KNN (optional, dung DEFAULT_KNN_CONFIG neu None)
                     Keys: enabled, price_method, target_method, ma_len,
                           target_ma_len, n_neighbors, smoothing_period

    Returns:
        StrategyResult da duoc modify (cung object, df_result da thay doi)
    """
    # Merge config: dung default, override bang knn_config tu strategy_list.json
    config = DEFAULT_KNN_CONFIG.copy()

    # Uu tien config tu StrategyResult.knn_filter_config (truyen tu engine)
    if hasattr(result, "knn_filter_config") and result.knn_filter_config:
        config.update(result.knn_filter_config)

    # Override bang tham so truyen truc tiep
    if knn_config:
        config.update(knn_config)

    # Kiem tra enabled
    if not config.get("enabled", True):
        logger.debug(
            f"[SignalFilter] KNN filter DISABLED cho '{result.strategy_name}' — giu signal goc"
        )
        return result

    df = result.df_result
    if df is None or df.empty:
        return result

    # Kiem tra cot can thiet
    required = ["high", "low", "close", "signal"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        logger.warning(
            f"[SignalFilter] Thieu cot {missing} trong df_result "
            f"cua '{result.strategy_name}' — bo qua filter"
        )
        return result

    try:
        # 1. Luu signal goc
        df["strategy_signal"] = df["signal"].copy()

        # 2. Chay KNN Trend
        knn_result = calculate_knn_trend(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            price_method=config.get("price_method", "hl2"),
            target_method=config.get("target_method", "rma"),
            ma_len=config.get("ma_len", 5),
            target_ma_len=config.get("target_ma_len", 5),
            n_neighbors=config.get("n_neighbors", 3),
            smoothing_period=config.get("smoothing_period", 50),
        )

        # 3. Them cac cot KNN vao DataFrame (phuc vu debug/dashboard)
        df["KNN_MA"]    = knn_result["knn_ma"]
        df["KNN_AVG"]   = knn_result["knn_avg"]
        df["KNN_PRED"]  = knn_result["knn_prediction"]
        df["KNN_COLOR"] = knn_result["knn_color"]

        # 4. Tao final signal
        strategy_sig = df["strategy_signal"].astype(float)
        knn_pred     = df["KNN_PRED"].astype(float)

        # BUY: strategy_signal == 1 AND knn_prediction > 0
        buy_pass = (strategy_sig == 1) & (knn_pred > 0)

        # SELL: strategy_signal == 2 AND knn_prediction < 0
        sell_pass = (strategy_sig == 2) & (knn_pred < 0)

        # Final signal: chi giu nhung signal duoc KNN confirm
        final_signal = pd.Series(0, index=df.index, dtype=int)
        final_signal[buy_pass]  = 1
        final_signal[sell_pass] = 2

        # 5. Ghi de signal
        df["signal"] = final_signal

        # 6. Clear entry/sl/tp cho cac signal bi filter bo
        filtered_mask = (df["strategy_signal"] != 0) & (df["signal"] == 0)
        for col in ["entry", "sl", "tp", "sl_distance", "tp_distance"]:
            if col in df.columns:
                df.loc[filtered_mask, col] = np.nan

        # 7. Update df_result
        result.df_result = df

        # 8. Log thong ke
        original_count = (df["strategy_signal"] != 0).sum()
        final_count    = (df["signal"] != 0).sum()
        filtered_count = original_count - final_count

        logger.info(
            f"[SignalFilter] '{result.strategy_name}' | "
            f"{result.provider}:{result.symbol}:{result.timeframe} | "
            f"Strategy signals: {original_count} | "
            f"KNN filtered: {filtered_count} | "
            f"Final signals: {final_count} "
            f"(BUY={(df['signal']==1).sum()} SELL={(df['signal']==2).sum()})"
        )

    except Exception as e:
        logger.error(
            f"[SignalFilter] Loi khi apply KNN filter cho "
            f"'{result.strategy_name}': {e}",
            exc_info=True,
        )
        # Neu loi, giu signal goc (khong filter)
        if "strategy_signal" in df.columns:
            df["signal"] = df["strategy_signal"]

    return result
