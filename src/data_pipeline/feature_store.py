"\"\"\"Feature engineering utilities for candle data.\"\"\""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd

from src.core.logging_config import get_logger
from src.data_pipeline.storage import DataStorage


@dataclass
class FeatureStore:
    """Transforms raw candle payloads into feature-rich tables."""

    storage: DataStorage

    def build_features(self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]) -> pd.DataFrame:
        """Create engineered features and persist them."""
        logger = get_logger("feature_store")
        frame = self._to_dataframe(candles)
        if frame.empty:
            logger.warning("Empty candle frame", extra={"symbol": symbol, "timeframe": timeframe})
            return frame

        frame = self._enrich(frame)
        path = self.storage.save_processed(symbol, timeframe, frame)
        logger.info("Features saved", extra={"symbol": symbol, "timeframe": timeframe, "path": str(path)})
        return frame

    @staticmethod
    def _to_dataframe(candles: List[Dict[str, Any]]) -> pd.DataFrame:
        frame = pd.DataFrame(candles)
        if frame.empty:
            return frame
        # Normalize columns expected from Kiwoom API.
        rename_map = {
            "stck_prpr": "close",
            "stck_oprc": "open",
            "stck_hgpr": "high",
            "stck_lwpr": "low",
            "cntg_vol": "volume",
            "stck_bsop_date": "date",
            "stck_cntg_hour": "time",
            "open_pric": "open",
            "high_pric": "high",
            "low_pric": "low",
            "close_pric": "close",
            "trde_qty": "volume",
            "trde_prica": "value",
        }
        frame = frame.rename(columns=rename_map)
        if "date" in frame and "time" in frame:
            frame["timestamp"] = pd.to_datetime(frame["date"] + frame["time"].str.zfill(6), format="%Y%m%d%H%M%S")
        elif "date" in frame:
            frame["timestamp"] = pd.to_datetime(frame["date"], format="%Y%m%d")
        frame = frame.sort_values("timestamp")
        return frame

    @staticmethod
    def _enrich(frame: pd.DataFrame) -> pd.DataFrame:
        # Basic returns & moving averages as placeholders for later RL/SL features.
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame["open"] = pd.to_numeric(frame["open"], errors="coerce")
        frame["high"] = pd.to_numeric(frame["high"], errors="coerce")
        frame["low"] = pd.to_numeric(frame["low"], errors="coerce")
        frame["volume"] = pd.to_numeric(frame.get("volume"), errors="coerce")
        frame["return"] = frame["close"].pct_change().fillna(0)
        frame["sma_5"] = frame["close"].rolling(window=5).mean().fillna(method="bfill")
        frame["sma_20"] = frame["close"].rolling(window=20).mean().fillna(method="bfill")
        frame["volatility"] = frame["return"].rolling(window=20).std().fillna(0)
        return frame
