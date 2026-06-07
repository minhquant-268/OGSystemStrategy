"""
test_signal_filter.py
=====================
Unit tests cho src/core/signal_filter.py
"""

import os
import sys
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.signal_filter import apply_knn_filter, DEFAULT_KNN_CONFIG
from src.core.strategy_engine import StrategyResult


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_result(signals: list, knn_filter_config: dict = None) -> StrategyResult:
    """Tao StrategyResult gia lap voi signal co san."""
    n = len(signals)
    df = pd.DataFrame({
        "date_time" : pd.date_range("2026-01-01", periods=n, freq="15min"),
        "open"      : np.linspace(100, 110, n),
        "high"      : np.linspace(101, 111, n),
        "low"       : np.linspace(99, 109, n),
        "close"     : np.linspace(100.5, 110.5, n),
        "volume"    : np.full(n, 1000.0),
        "signal"    : signals,
        "entry"     : np.linspace(100, 110, n),
        "sl"        : np.linspace(99, 109, n),
        "tp"        : np.linspace(102, 112, n),
        "sl_distance" : np.full(n, 1.0),
        "tp_distance" : np.full(n, 2.0),
    })
    return StrategyResult(
        strategy_name="testStrategy",
        provider="TEST",
        symbol="XYZUSD",
        timeframe="15",
        df_result=df,
        knn_filter_config=knn_filter_config or {},
    )


def _mock_knn(predictions: list):
    """Tra ve ham mock cho calculate_knn_trend voi knn_prediction co san."""
    n = len(predictions)
    idx = pd.RangeIndex(n)

    def _inner(high, low, close, **kwargs):
        return {
            "knn_ma"         : pd.Series(np.ones(n), index=high.index),
            "knn_avg"        : pd.Series(np.ones(n), index=high.index),
            "knn_prediction" : pd.Series(predictions, index=high.index, dtype=float),
            "knn_color"      : pd.Series(np.ones(n, dtype=int), index=high.index),
            "cross_over_avg" : pd.Series([False] * n, index=high.index),
            "cross_under_avg": pd.Series([False] * n, index=high.index),
            "switch_up"      : pd.Series([False] * n, index=high.index),
            "switch_down"    : pd.Series([False] * n, index=high.index),
        }

    return _inner


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyKnnFilter:

    # --- enabled=False: giu nguyen signal goc ---

    def test_disabled_keeps_original_signal(self):
        result = _make_result([0, 1, 2, 1, 0])
        result = apply_knn_filter(result, knn_config={"enabled": False})
        signals = result.df_result["signal"].tolist()
        assert signals == [0, 1, 2, 1, 0]

    def test_disabled_no_strategy_signal_column(self):
        """Khi disabled, khong them cot strategy_signal."""
        result = _make_result([1, 2])
        result = apply_knn_filter(result, knn_config={"enabled": False})
        assert "strategy_signal" not in result.df_result.columns

    # --- BUY confirm: strategy=1, knn>0 -> final=1 ---

    def test_buy_confirmed_when_knn_bullish(self):
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn([1.0, 1.0, 1.0])):
            result = _make_result([0, 1, 0])
            result = apply_knn_filter(result)
        assert result.df_result["signal"].tolist() == [0, 1, 0]

    # --- SELL confirm: strategy=2, knn<0 -> final=2 ---

    def test_sell_confirmed_when_knn_bearish(self):
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn([-1.0, -1.0, -1.0])):
            result = _make_result([0, 2, 0])
            result = apply_knn_filter(result)
        assert result.df_result["signal"].tolist() == [0, 2, 0]

    # --- BUY bi filter: strategy=1, knn<0 -> final=0, entry/sl/tp=NaN ---

    def test_buy_filtered_when_knn_bearish(self):
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn([-1.0, -1.0])):
            result = _make_result([1, 1])
            result = apply_knn_filter(result)
        df = result.df_result
        assert df["signal"].tolist() == [0, 0]
        assert df["entry"].isna().all()
        assert df["sl"].isna().all()
        assert df["tp"].isna().all()

    # --- SELL bi filter: strategy=2, knn>0 -> final=0, entry/sl/tp=NaN ---

    def test_sell_filtered_when_knn_bullish(self):
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn([1.0, 1.0])):
            result = _make_result([2, 2])
            result = apply_knn_filter(result)
        df = result.df_result
        assert df["signal"].tolist() == [0, 0]
        assert df["entry"].isna().all()
        assert df["sl"].isna().all()
        assert df["tp"].isna().all()

    # --- BUY bi filter: knn neutral (0) -> final=0 ---

    def test_buy_filtered_when_knn_neutral(self):
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn([0.0, 0.0])):
            result = _make_result([1, 1])
            result = apply_knn_filter(result)
        assert result.df_result["signal"].tolist() == [0, 0]

    # --- SELL bi filter: knn neutral (0) -> final=0 ---

    def test_sell_filtered_when_knn_neutral(self):
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn([0.0, 0.0])):
            result = _make_result([2, 2])
            result = apply_knn_filter(result)
        assert result.df_result["signal"].tolist() == [0, 0]

    # --- strategy_signal luu dung gia tri goc ---

    def test_strategy_signal_preserved(self):
        original = [0, 1, 2, 0, 1]
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn([-1.0] * 5)):
            result = _make_result(original)
            result = apply_knn_filter(result)
        df = result.df_result
        assert "strategy_signal" in df.columns
        assert df["strategy_signal"].tolist() == [float(s) for s in original]

    # --- HOLD goc (signal=0) khong bi anh huong ---

    def test_hold_rows_remain_hold(self):
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn([1.0, -1.0, 0.0])):
            result = _make_result([0, 0, 0])
            result = apply_knn_filter(result)
        assert result.df_result["signal"].tolist() == [0, 0, 0]

    # --- KNN columns duoc them vao df ---

    def test_knn_columns_added(self):
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn([1.0])):
            result = _make_result([0])
            result = apply_knn_filter(result)
        for col in ["KNN_MA", "KNN_AVG", "KNN_PRED", "KNN_COLOR"]:
            assert col in result.df_result.columns, f"Thieu cot {col}"

    # --- Mix signals: buy+bullish pass, sell+bullish filtered ---

    def test_mixed_signals(self):
        #               buy+bull  sell+bull  buy+bear  sell+bear  hold+any
        signals = [1,        2,        1,        2,        0]
        knn     = [1.0,     1.0,     -1.0,    -1.0,      1.0]
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn(knn)):
            result = _make_result(signals)
            result = apply_knn_filter(result)
        expected = [1, 0, 0, 2, 0]
        assert result.df_result["signal"].tolist() == expected

    # --- entry/sl/tp giu nguyen khi khong bi filter ---

    def test_entry_sl_tp_preserved_when_signal_passes(self):
        with patch("src.core.signal_filter.calculate_knn_trend",
                   side_effect=_mock_knn([1.0])):
            result = _make_result([1])
            original_entry = result.df_result["entry"].iloc[0]
            result = apply_knn_filter(result)
        assert not pd.isna(result.df_result["entry"].iloc[0])
        assert result.df_result["entry"].iloc[0] == original_entry

    # --- df rong: khong crash, tra ve nguyen result ---

    def test_empty_df_no_crash(self):
        result = StrategyResult(
            strategy_name="empty",
            provider="TEST",
            symbol="X",
            timeframe="15",
            df_result=pd.DataFrame(),
        )
        returned = apply_knn_filter(result)
        assert returned is result
        assert returned.df_result.empty

    # --- df=None: khong crash ---

    def test_none_df_no_crash(self):
        result = StrategyResult(
            strategy_name="none_df",
            provider="TEST",
            symbol="X",
            timeframe="15",
            df_result=None,
        )
        returned = apply_knn_filter(result)
        assert returned is result

    # --- KNN crash: fallback ve signal goc ---

    def test_knn_error_fallback_to_original(self):
        def _crash(*args, **kwargs):
            raise RuntimeError("KNN error")

        with patch("src.core.signal_filter.calculate_knn_trend", side_effect=_crash):
            result = _make_result([0, 1, 2])
            result = apply_knn_filter(result)

        # Khi KNN loi, signal phai duoc roll back ve signal goc
        assert result.df_result["signal"].tolist() == [0, 1, 2]

    # --- knn_filter_config tu StrategyResult duoc uu tien ---

    def test_knn_filter_config_from_result_used(self):
        """knn_filter_config.enabled=False tren StrategyResult phai disable filter."""
        result = _make_result([1, 2], knn_filter_config={"enabled": False})
        result = apply_knn_filter(result)
        assert result.df_result["signal"].tolist() == [1, 2]
