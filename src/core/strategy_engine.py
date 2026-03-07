"""
strategy_engine.py
==================
Engine trung tam dieu phoi viec chay cac strategy.

Trach nhiem:
    1. Load danh sach strategy tu config/strategy_list.json
    2. Voi moi strategy enabled, khoi tao instance qua dynamic import
    3. Voi moi (provider, symbol, timeframe) trong config:
        - Loc DataFrame dau vao theo dung cap (provider, symbol, timeframe) do
        - Goi strategy.calculate_signals(df_filtered) -> df_result
    4. Tra ve danh sach StrategyResult

Luu y:
    - Strategy KHONG tu loc du lieu. Engine loc truoc khi goi strategy.
    - Moi cap (provider, symbol, timeframe) duoc xu ly doc lap.
    - Engine khong phu thuoc vao DB hay Redis — nhung thu do keyspace_monitor lo.

Cach su dung:
    engine = StrategyEngine(config_path="config/strategy_list.json")
    results = engine.run(df)  # df co the chua nhieu symbol/timeframe
    for r in results:
        print(r.strategy_name, r.symbol, r.timeframe, r.df_result)
"""

import importlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StrategyResult:
    """Ket qua chay 1 strategy tren 1 cap (symbol, timeframe)."""
    strategy_name : str
    provider      : str
    symbol        : str
    timeframe     : str
    df_result     : pd.DataFrame


@dataclass
class StrategyConfig:
    """Cau hinh 1 strategy doc tu strategy_list.json."""
    name      : str
    enabled   : bool
    class_    : str   # duong dan import (vd: src.strategies.strategy_comboATR.ComboATRStrategy)
    symbols   : Any   # list[str] | "all"
    timeframes: Any   # list[str] | "all"


# ─────────────────────────────────────────────────────────────────────────────
# StrategyEngine
# ─────────────────────────────────────────────────────────────────────────────

class StrategyEngine:
    """
    Engine dieu phoi cac strategy.

    Args:
        config_path : Duong dan toi strategy_list.json.
                      Mac dinh: "config/strategy_list.json"
    """

    DEFAULT_CONFIG = "config/strategy_list.json"

    def __init__(self, config_path: str = None):
        self.config_path = config_path or self.DEFAULT_CONFIG
        self._configs: List[StrategyConfig] = []
        self._load_config()

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config(self) -> None:
        """Doc va parse strategy_list.json."""
        try:
            if not os.path.exists(self.config_path):
                logger.error(f"[StrategyEngine] Khong tim thay config: {self.config_path}")
                return

            with open(self.config_path, encoding="utf-8") as f:
                raw = json.load(f)

            self._configs = []
            for item in raw:
                cfg = StrategyConfig(
                    name       = item["name"],
                    enabled    = item.get("enabled", True),
                    class_     = item["class"],
                    symbols    = item.get("symbols", "all"),
                    timeframes = item.get("timeframes", "all"),
                )
                self._configs.append(cfg)

            enabled = [c.name for c in self._configs if c.enabled]
            logger.info(
                f"[StrategyEngine] Loaded {len(self._configs)} strategies, "
                f"enabled: {enabled}"
            )

        except Exception as e:
            logger.error(f"[StrategyEngine] Loi load config: {e}", exc_info=True)

    def reload_config(self) -> None:
        """Reload config tu file (dung khi config thay doi luc runtime)."""
        self._load_config()

    # ── Dynamic import ─────────────────────────────────────────────────────────

    @staticmethod
    def _import_strategy(class_path: str):
        """
        Import va khoi tao strategy class tu duong dan day du.
        Strategy duoc khoi tao voi gia tri mac dinh cua __init__.
        De tuy chinh params, sua truc tiep trong class strategy.

        Args:
            class_path : Vi du "src.strategies.strategy_comboATR.ComboATRStrategy"

        Returns:
            Instance cua strategy, hoac None neu loi.
        """
        try:
            parts      = class_path.rsplit(".", 1)
            module_path, class_name = parts[0], parts[1]
            module     = importlib.import_module(module_path)
            cls        = getattr(module, class_name)
            instance   = cls()   # khoi tao voi default params
            return instance
        except Exception as e:
            logger.error(
                f"[StrategyEngine] Khong the import/khoi tao '{class_path}': {e}",
                exc_info=True,
            )
            return None

    # ── Filtering ──────────────────────────────────────────────────────────────

    @staticmethod
    def _filter_df(
        df: pd.DataFrame,
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> pd.DataFrame:
        """
        Loc DataFrame theo (provider, symbol, timeframe).

        Chi loc theo cac cot ton tai trong df:
        - Neu df co cot 'symbol'   -> loc theo symbol
        - Neu df co cot 'provider' -> loc theo provider
        - Neu df co cot 'timeframe'-> loc theo timeframe
        - Sap xep theo date_time (neu co)
        """
        mask = pd.Series(True, index=df.index)

        if "provider" in df.columns and provider:
            mask = mask & (df["provider"].astype(str) == str(provider))
        if "symbol" in df.columns and symbol:
            mask = mask & (df["symbol"].astype(str) == str(symbol))
        if "timeframe" in df.columns and timeframe:
            mask = mask & (df["timeframe"].astype(str) == str(timeframe))

        filtered = df.loc[mask].copy()

        if "date_time" in filtered.columns and not filtered.empty:
            filtered = filtered.sort_values("date_time").reset_index(drop=True)

        return filtered

    # ── Main run ───────────────────────────────────────────────────────────────

    def run(self, df: pd.DataFrame) -> List[StrategyResult]:
        """
        Chay tat ca strategy enabled tren DataFrame dau vao.

        Args:
            df : DataFrame chứa du lieu nen. Co the chua nhieu (symbol, timeframe).
                 Cac cot thuong co: [date_time, provider, symbol, timeframe,
                                     open, high, low, close, volume]

        Returns:
            Danh sach StrategyResult, moi phan tu la ket qua cua 1 strategy
            tren 1 cap (provider, symbol, timeframe).
        """
        results: List[StrategyResult] = []

        if not isinstance(df, pd.DataFrame) or df.empty:
            logger.warning("[StrategyEngine] DataFrame dau vao rong hoac khong hop le.")
            return results

        for cfg in self._configs:
            if not cfg.enabled:
                logger.debug(f"[StrategyEngine] Strategy '{cfg.name}' bi tat. Bo qua.")
                continue

            # Khoi tao strategy instance (dung default params cua class)
            strategy = self._import_strategy(cfg.class_)
            if strategy is None:
                continue

            # Xac dinh danh sach (provider, symbol, timeframe) can chay
            sym_list = self._resolve_symbol_list(cfg, df)
            if not sym_list:
                logger.warning(
                    f"[StrategyEngine] Strategy '{cfg.name}': "
                    "Khong co (symbol, timeframe) nao khop. Bo qua."
                )
                continue

            for sym_cfg in sym_list:
                provider  = sym_cfg.get("provider", "")
                symbol    = sym_cfg.get("symbol", "")
                timeframe = sym_cfg.get("timeframe", "")

                df_filtered = self._filter_df(df, provider, symbol, timeframe)

                if df_filtered.empty:
                    logger.debug(
                        f"[StrategyEngine][{cfg.name}] Khong co du lieu cho "
                        f"provider={provider}, symbol={symbol}, tf={timeframe}. Bo qua."
                    )
                    continue

                logger.info(
                    f"[StrategyEngine] Chay '{cfg.name}' | "
                    f"provider={provider} symbol={symbol} tf={timeframe} | "
                    f"{len(df_filtered)} nen"
                )

                try:
                    df_result = strategy.calculate_signals(df_filtered)
                    results.append(StrategyResult(
                        strategy_name = cfg.name,
                        provider      = provider,
                        symbol        = symbol,
                        timeframe     = timeframe,
                        df_result     = df_result,
                    ))
                except Exception as e:
                    logger.error(
                        f"[StrategyEngine] Loi khi chay '{cfg.name}' "
                        f"({symbol}/{timeframe}): {e}",
                        exc_info=True,
                    )

        return results

    def _resolve_symbol_list(
        self, cfg: StrategyConfig, df: pd.DataFrame
    ) -> List[Dict[str, str]]:
        """
        Tra ve danh sach {symbol, timeframe} can xu ly,
        la cartesian product cua cfg.symbols x cfg.timeframes.

        Rules:
            symbols="all"    -> lay tat ca symbol duy nhat trong df
            timeframes="all" -> lay tat ca timeframe duy nhat trong df
            symbols=[...]    -> dung danh sach do
            timeframes=[...] -> dung danh sach do
        """
        # Xac dinh danh sach symbol
        if cfg.symbols == "all":
            sym_list = df["symbol"].unique().tolist() if "symbol" in df.columns else [""]
        elif isinstance(cfg.symbols, list):
            sym_list = [str(s) for s in cfg.symbols]
        else:
            sym_list = []

        # Xac dinh danh sach timeframe
        if cfg.timeframes == "all":
            tf_list = df["timeframe"].unique().tolist() if "timeframe" in df.columns else [""]
        elif isinstance(cfg.timeframes, list):
            tf_list = [str(t) for t in cfg.timeframes]
        else:
            tf_list = []

        if not sym_list or not tf_list:
            return []

        # Cartesian product: moi (symbol, timeframe)
        return [
            {"provider": "", "symbol": sym, "timeframe": tf}
            for sym in sym_list
            for tf in tf_list
        ]
