"""
test_strategies.py
==================
Unit test cho:
    - Tung strategy (ComboATR, MACrossover, RSI)
    - StrategyEngine (load config, filter, run)

Chay:
    pytest tests/test_strategies.py -v
    pytest tests/test_strategies.py -v -k "TestComboATR"
"""

import os
import sys
import json
import pytest
import numpy as np
import pandas as pd

# Them project root vao path de import src.*
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.strategies.strategy_comboATR import ComboATRStrategy
from src.strategies.strategy_MAcrossover import MACrossoverStrategy
from src.strategies.strategy_RSI import RSIStrategy
from src.core.strategy_engine import StrategyEngine, StrategyResult


# ─────────────────────────────────────────────────────────────────────────────
# Helpers tao du lieu test
# ─────────────────────────────────────────────────────────────────────────────

def make_ohlcv(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """
    Tao DataFrame OHLCV don gian (khong co metadata symbol/timeframe).
    Dung de test tung strategy truc tiep.
    """
    np.random.seed(seed)
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100.0)
    high  = close + np.abs(np.random.randn(n)) * 0.5
    low   = close - np.abs(np.random.randn(n)) * 0.5
    open_ = close.shift(1).fillna(close.iloc[0])
    return pd.DataFrame({
        "date_time" : pd.date_range("2025-01-01", periods=n, freq="15min"),
        "open"      : open_,
        "high"      : high,
        "low"       : low,
        "close"     : close,
        "volume"    : np.random.randint(100, 1000, n).astype(float),
    })


def make_multi_symbol_df(
    symbols: list = None,
    timeframes: list = None,
    n: int = 100,
) -> pd.DataFrame:
    """
    Tao DataFrame với nhieu symbol va timeframe (co cot provider, symbol, timeframe).
    Dung de test StrategyEngine filter.
    """
    if symbols is None:
        symbols = ["BTCUSD", "ETHUSD"]
    if timeframes is None:
        timeframes = ["10", "15"]

    parts = []
    for sym in symbols:
        for tf in timeframes:
            df = make_ohlcv(n=n, seed=hash((sym, tf)) % 10000)
            df["provider"]  = "CAPITALCOM"
            df["symbol"]    = sym
            df["timeframe"] = tf
            parts.append(df)

    return pd.concat(parts, ignore_index=True)


SIGNAL_COLS = ["signal", "entry", "sl", "tp", "sl_distance", "tp_distance"]
REQUIRED_OUTPUT_COLS = ["signal"]


# ─────────────────────────────────────────────────────────────────────────────
# Test ComboATRStrategy
# ─────────────────────────────────────────────────────────────────────────────

class TestComboATR:
    """Test ComboATRStrategy doc lap, khong qua engine."""

    def setup_method(self):
        self.strategy = ComboATRStrategy(
            macd_fast=5, macd_slow=25, macd_signal=5,
            sma_period=20, atr_period=5, kSL=2.3, kTP=5.3,
        )
        self.df = make_ohlcv(n=200)

    def test_returns_dataframe(self):
        result = self.strategy.calculate_signals(self.df)
        assert isinstance(result, pd.DataFrame)

    def test_signal_column_exists(self):
        result = self.strategy.calculate_signals(self.df)
        assert "signal" in result.columns

    def test_signal_values_valid(self):
        result = self.strategy.calculate_signals(self.df)
        assert result["signal"].isin([0, 1, 2]).all()

    def test_indicator_columns_exist(self):
        result = self.strategy.calculate_signals(self.df)
        for col in ["MACD", "MACD_Signal", "MACD_Hist", "SMA", "ATR"]:
            assert col in result.columns, f"Missing column: {col}"

    def test_sl_tp_exist_when_signal(self):
        result = self.strategy.calculate_signals(self.df)
        signal_rows = result[result["signal"] != 0]
        if not signal_rows.empty:
            for col in ["entry", "sl", "tp"]:
                assert signal_rows[col].notna().all(), f"NaN found in {col} where signal != 0"

    def test_buy_sl_below_entry(self):
        result = self.strategy.calculate_signals(self.df)
        buy_rows = result[result["signal"] == 1]
        if not buy_rows.empty:
            assert (buy_rows["sl"] < buy_rows["entry"]).all(), "BUY SL phai duoi entry"

    def test_buy_tp_above_entry(self):
        result = self.strategy.calculate_signals(self.df)
        buy_rows = result[result["signal"] == 1]
        if not buy_rows.empty:
            assert (buy_rows["tp"] > buy_rows["entry"]).all(), "BUY TP phai tren entry"

    def test_sell_sl_above_entry(self):
        result = self.strategy.calculate_signals(self.df)
        sell_rows = result[result["signal"] == 2]
        if not sell_rows.empty:
            assert (sell_rows["sl"] > sell_rows["entry"]).all(), "SELL SL phai tren entry"

    def test_sell_tp_below_entry(self):
        result = self.strategy.calculate_signals(self.df)
        sell_rows = result[result["signal"] == 2]
        if not sell_rows.empty:
            assert (sell_rows["tp"] < sell_rows["entry"]).all(), "SELL TP phai duoi entry"

    def test_no_repeat_signals(self):
        """Khong co 2 BUY lien tiep hay 2 SELL lien tiep."""
        result = self.strategy.calculate_signals(self.df)
        sigs = result[result["signal"] != 0]["signal"].tolist()
        for i in range(1, len(sigs)):
            assert sigs[i] != sigs[i - 1], "Co 2 tin hieu cung chieu lien tiep"

    def test_row_count_preserved(self):
        result = self.strategy.calculate_signals(self.df)
        assert len(result) == len(self.df)

    def test_empty_df_returns_gracefully(self):
        empty = pd.DataFrame(columns=["open", "high", "low", "close"])
        result = self.strategy.calculate_signals(empty)
        assert isinstance(result, pd.DataFrame)

    def test_get_indicators_returns_dict(self):
        result = self.strategy.calculate_signals(self.df)
        indicators = self.strategy.get_indicators(result)
        assert isinstance(indicators, dict)
        assert "macd" in indicators
        assert "sma" in indicators


# ─────────────────────────────────────────────────────────────────────────────
# Test MACrossoverStrategy
# ─────────────────────────────────────────────────────────────────────────────

class TestMACrossover:
    """Test MACrossoverStrategy doc lap."""

    def setup_method(self):
        self.strategy = MACrossoverStrategy(
            short_period=10, long_period=30, atr_period=5, kSL=2.0, kTP=4.0,
        )
        self.df = make_ohlcv(n=200)

    def test_returns_dataframe(self):
        result = self.strategy.calculate_signals(self.df)
        assert isinstance(result, pd.DataFrame)

    def test_signal_column_exists(self):
        result = self.strategy.calculate_signals(self.df)
        assert "signal" in result.columns

    def test_signal_values_valid(self):
        result = self.strategy.calculate_signals(self.df)
        assert result["signal"].isin([0, 1, 2]).all()

    def test_ma_columns_exist(self):
        result = self.strategy.calculate_signals(self.df)
        assert "MA_Short" in result.columns
        assert "MA_Long" in result.columns
        assert "ATR" in result.columns

    def test_sl_tp_valid_on_signals(self):
        result = self.strategy.calculate_signals(self.df)
        signal_rows = result[result["signal"] != 0]
        if not signal_rows.empty:
            for col in ["entry", "sl", "tp"]:
                assert signal_rows[col].notna().all()

    def test_row_count_preserved(self):
        result = self.strategy.calculate_signals(self.df)
        assert len(result) == len(self.df)


# ─────────────────────────────────────────────────────────────────────────────
# Test RSIStrategy
# ─────────────────────────────────────────────────────────────────────────────

class TestRSI:
    """Test RSIStrategy doc lap."""

    def setup_method(self):
        from src.strategies.strategy_RSI import RSIStrategy
        self.strategy = RSIStrategy(
            rsi_period=14, overbought=70.0, oversold=30.0,
            atr_period=5, kSL=1.5, kTP=3.0,
        )
        self.df = make_ohlcv(n=200)

    def test_returns_dataframe(self):
        result = self.strategy.calculate_signals(self.df)
        assert isinstance(result, pd.DataFrame)

    def test_signal_values_valid(self):
        result = self.strategy.calculate_signals(self.df)
        assert result["signal"].isin([0, 1, 2]).all()

    def test_rsi_column_exists(self):
        result = self.strategy.calculate_signals(self.df)
        assert "RSI" in result.columns

    def test_rsi_range(self):
        result = self.strategy.calculate_signals(self.df)
        rsi_vals = result["RSI"].dropna()
        assert (rsi_vals >= 0).all() and (rsi_vals <= 100).all()

    def test_row_count_preserved(self):
        result = self.strategy.calculate_signals(self.df)
        assert len(result) == len(self.df)


# ─────────────────────────────────────────────────────────────────────────────
# Test StrategyEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategyEngine:
    """Test StrategyEngine: load config, filter, run."""

    CONFIG_PATH = os.path.join(
        os.path.dirname(__file__), "..", "config", "strategy_list.json"
    )

    def setup_method(self):
        self.engine = StrategyEngine(config_path=self.CONFIG_PATH)

    # ── Load config ───────────────────────────────────────────────────────────

    def test_config_loads(self):
        assert len(self.engine._configs) > 0, "Khong load duoc config"

    def test_config_has_enabled_strategies(self):
        enabled = [c for c in self.engine._configs if c.enabled]
        assert len(enabled) > 0, "Khong co strategy nao duoc bat"

    # ── Filter ────────────────────────────────────────────────────────────────

    def test_filter_by_symbol(self):
        df = make_multi_symbol_df(symbols=["BTCUSD", "ETHUSD"], timeframes=["10"])
        filtered = StrategyEngine._filter_df(df, "", "BTCUSD", "10")
        assert (filtered["symbol"] == "BTCUSD").all()
        assert len(filtered) > 0

    def test_filter_by_provider_symbol_timeframe(self):
        df = make_multi_symbol_df(symbols=["BTCUSD"], timeframes=["10", "15"])
        filtered = StrategyEngine._filter_df(df, "CAPITALCOM", "BTCUSD", "10")
        assert (filtered["timeframe"] == "10").all()
        assert len(filtered) > 0

    def test_filter_returns_sorted_by_datetime(self):
        df = make_multi_symbol_df(symbols=["BTCUSD"], timeframes=["10"])
        filtered = StrategyEngine._filter_df(df, "CAPITALCOM", "BTCUSD", "10")
        dates = filtered["date_time"].tolist()
        assert dates == sorted(dates)

    def test_filter_empty_when_no_match(self):
        df = make_multi_symbol_df(symbols=["BTCUSD"], timeframes=["10"])
        filtered = StrategyEngine._filter_df(df, "CAPITALCOM", "XYZXYZ", "10")
        assert filtered.empty

    # ── Run ───────────────────────────────────────────────────────────────────

    def test_run_returns_list(self):
        df = make_multi_symbol_df(symbols=["BTCUSD"], timeframes=["10", "15"])
        results = self.engine.run(df)
        assert isinstance(results, list)

    def test_run_with_matching_symbols(self):
        """ComboATR config co BTCUSD/5 va BTCUSD/15, phai tra ve 2 result."""
        df = make_multi_symbol_df(symbols=["BTCUSD"], timeframes=["5", "15"])
        results = self.engine.run(df)
        combo_results = [r for r in results if r.strategy_name == "comboATR"]
        assert len(combo_results) == 2, (
            f"Expected 2 results for comboATR (BTCUSD/5 + BTCUSD/15), got {len(combo_results)}"
        )

    def test_run_result_has_signal_column(self):
        df = make_multi_symbol_df(symbols=["BTCUSD"], timeframes=["10"])
        results = self.engine.run(df)
        for r in results:
            assert "signal" in r.df_result.columns, (
                f"{r.strategy_name}/{r.symbol}/{r.timeframe}: missing 'signal' column"
            )

    def test_run_result_signal_values_valid(self):
        df = make_multi_symbol_df(symbols=["BTCUSD"], timeframes=["10"])
        results = self.engine.run(df)
        for r in results:
            assert r.df_result["signal"].isin([0, 1, 2]).all(), (
                f"{r.strategy_name}: invalid signal values"
            )

    def test_run_result_metadata(self):
        """Ket qua chua dung symbol/timeframe da khai bao."""
        df = make_multi_symbol_df(symbols=["BTCUSD"], timeframes=["10"])
        results = self.engine.run(df)
        for r in results:
            assert isinstance(r, StrategyResult)
            assert r.strategy_name
            assert r.symbol
            assert r.timeframe
            assert isinstance(r.df_result, pd.DataFrame)

    def test_run_empty_df_returns_empty_list(self):
        empty = pd.DataFrame()
        results = self.engine.run(empty)
        assert results == []

    def test_run_symbols_all(self, tmp_path):
        """Strategy voi symbols='all' phai chay cho tat ca combination trong df."""
        config = [
            {
                "name": "test_all",
                "enabled": True,
                "class": "src.strategies.strategy_comboATR.ComboATRStrategy",
                "params": {},
                "symbols": "all",
            }
        ]
        config_file = tmp_path / "test_strategy_list.json"
        config_file.write_text(json.dumps(config))

        engine = StrategyEngine(config_path=str(config_file))
        df = make_multi_symbol_df(symbols=["BTCUSD", "ETHUSD"], timeframes=["10", "15"])
        results = engine.run(df)

        # 2 symbols x 2 timeframes = 4 results
        assert len(results) == 4, f"Expected 4 results, got {len(results)}"

    def test_disabled_strategy_skipped(self, tmp_path):
        """Strategy voi enabled=false khong duoc chay."""
        config = [
            {
                "name": "disabled_test",
                "enabled": False,
                "class": "src.strategies.strategy_comboATR.ComboATRStrategy",
                "params": {},
                "symbols": "all",
            }
        ]
        config_file = tmp_path / "disabled.json"
        config_file.write_text(json.dumps(config))

        engine = StrategyEngine(config_path=str(config_file))
        df = make_multi_symbol_df(symbols=["BTCUSD"], timeframes=["10"])
        results = engine.run(df)
        assert results == []

    def test_invalid_class_path_skipped(self, tmp_path):
        """Strategy voi class path sai khong lam crash engine."""
        config = [
            {
                "name": "bad_class",
                "enabled": True,
                "class": "src.strategies.non_existent.NonExistentStrategy",
                "params": {},
                "symbols": "all",
            }
        ]
        config_file = tmp_path / "bad.json"
        config_file.write_text(json.dumps(config))

        engine = StrategyEngine(config_path=str(config_file))
        df = make_multi_symbol_df(symbols=["BTCUSD"], timeframes=["10"])
        results = engine.run(df)
        assert results == []  # Khong crash, tra ve list rong


# ─────────────────────────────────────────────────────────────────────────────
# Quick smoke test (chay truc tiep voi python, khong can pytest)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("SMOKE TEST — Strategy + Engine")
    print("=" * 60)

    df_single = make_ohlcv(n=150)
    df_multi  = make_multi_symbol_df(
        symbols=["BTCUSD", "ETHUSD"],
        timeframes=["10", "15"],
        n=150,
    )

    # --- Test tung strategy ---
    for Cls, kwargs, name in [
        (ComboATRStrategy,   {"macd_fast": 5, "macd_slow": 25, "macd_signal": 5, "sma_period": 20, "atr_period": 5}, "ComboATR"),
        (MACrossoverStrategy, {"short_period": 10, "long_period": 30, "atr_period": 5}, "MACrossover"),
        (RSIStrategy,        {"rsi_period": 14, "overbought": 70, "oversold": 30, "atr_period": 5}, "RSI"),
    ]:
        s = Cls(**kwargs)
        r = s.calculate_signals(df_single)
        buys  = (r["signal"] == 1).sum()
        sells = (r["signal"] == 2).sum()
        print(f"  [{name}] {len(r)} nen | BUY={buys} SELL={sells} | OK")

    print()

    # --- Test engine ---
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "strategy_list.json")
    engine  = StrategyEngine(config_path=config_path)
    results = engine.run(df_multi)

    print(f"  [StrategyEngine] {len(results)} results:")
    for r in results:
        buys  = (r.df_result["signal"] == 1).sum()
        sells = (r.df_result["signal"] == 2).sum()
        print(
            f"    strategy={r.strategy_name:<15} "
            f"symbol={r.symbol:<8} tf={r.timeframe:<5} | "
            f"{len(r.df_result)} nen | BUY={buys} SELL={sells}"
        )

    print()
    print("ALL SMOKE TESTS PASSED")
