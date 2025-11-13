"""High-level orchestration for data synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

from src.api.kiwoom_client import KiwoomRESTClient
from src.core.exceptions import KiwoomAPIError, MLStockError
from src.core.logging_config import get_logger
from src.core.settings import AppSettings, get_settings
from src.data_pipeline.collectors.candle_collector import CandleCollector
from src.data_pipeline.feature_store import FeatureStore
from src.data_pipeline.storage import DataStorage


@dataclass
class DataSyncConfig:
    """Configuration for synchronization runs."""

    symbols: Sequence[str]
    timeframes: Sequence[str]
    candles_per_request: int = 200
    full_history: bool = False


class DataSyncService:
    """Coordinates collectors, storage, and feature engineering."""

    def __init__(
        self,
        *,
        settings: AppSettings | None = None,
        storage: DataStorage | None = None,
        client: KiwoomRESTClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or DataStorage(root=self.settings.paths.root / "data")
        self.client = client or KiwoomRESTClient(settings=self.settings)
        self.feature_store = FeatureStore(storage=self.storage)
        self.logger = get_logger("data_sync")
        from src.symbols.registry import SymbolRegistry  # avoid circular

        self.symbol_registry = SymbolRegistry()

    def run(self, config: DataSyncConfig) -> Dict[str, Any]:
        """Synchronize candles for requested symbols/timeframes."""
        summary: Dict[str, Any] = {"synced": []}
        for symbol in config.symbols:
            for timeframe in config.timeframes:
                self.logger.info("Sync start", extra={"symbol": symbol, "timeframe": timeframe})
                candles = self._fetch_candles(
                    symbol,
                    timeframe,
                    config.candles_per_request,
                    full_history=config.full_history,
                )
                raw_path = self.storage.save_raw(symbol, timeframe, candles)
                rows = list(candles.get("output") or candles.get("stk_ddwkmm") or [])
                listing_date = self._listing_date(symbol)
                if listing_date:
                    rows = [row for row in rows if self._row_timestamp(row) >= listing_date]
                frame = self.feature_store.build_features(symbol, timeframe, rows)
                csv_path = self.storage.save_raw_csv(symbol, timeframe, rows)
                summary["synced"].append(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "rows": len(frame),
                        "raw_path": str(raw_path),
                        "csv_path": str(csv_path) if csv_path else "",
                    }
                )
        return summary

    def _fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int,
        *,
        full_history: bool = False,
    ) -> Dict[str, Any]:
        collector = CandleCollector(client=self.client, timeframe=timeframe, count=count)
        try:
            if full_history:
                return collector.run_full_history(symbol)
            return collector.run(symbol)
        except (KiwoomAPIError, MLStockError) as exc:
            self.logger.error("Collector failed, generating synthetic candles: %s", exc)
            return self._generate_synthetic_candles(symbol, timeframe, count)

    def _generate_synthetic_candles(self, symbol: str, timeframe: str, count: int) -> Dict[str, Any]:
        """Provide deterministic placeholder data when API access fails (useful for development/offline)."""
        import math
        from datetime import datetime, timedelta

        base = datetime.utcnow()
        candles: List[Dict[str, Any]] = []
        for i in range(count):
            t = base - timedelta(minutes=i)
            price = 70000 + 1000 * math.sin(i / 5)
            candles.append(
                {
                    "stck_prpr": price,
                    "stck_oprc": price - 50,
                    "stck_hgpr": price + 100,
                    "stck_lwpr": price - 100,
                    "cntg_vol": 1000 + i,
                    "stck_bsop_date": t.strftime("%Y%m%d"),
                    "stck_cntg_hour": t.strftime("%H%M%S"),
                }
            )
        candles.reverse()
        return {"output": candles, "symbol": symbol, "timeframe": timeframe, "synthetic": True}

    def _listing_date(self, symbol: str) -> Optional[pd.Timestamp]:
        record = self.symbol_registry.get(symbol)
        return pd.to_datetime(record.listing_date) if record else None

    @staticmethod
    def _row_timestamp(row: Dict[str, Any]) -> pd.Timestamp:
        date = row.get("stck_bsop_date") or row.get("date")
        time = row.get("stck_cntg_hour") or row.get("time") or "000000"
        ts_str = f"{date}{time.zfill(6)}"
        return pd.to_datetime(ts_str, format="%Y%m%d%H%M%S")
