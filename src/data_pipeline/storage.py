"""Filesystem storage helpers for raw and processed market data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class DataStorage:
    """Persists raw API payloads and processed feature tables."""

    root: Path

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.root / "processed"

    def save_raw(self, symbol: str, timeframe: str, payload: Dict[str, Any]) -> Path:
        """Persist raw JSON payload for traceability."""
        path = self.raw_dir / symbol / timeframe
        path.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        file_path = path / f"{ts}.json"
        with file_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return file_path

    def save_processed(self, symbol: str, timeframe: str, frame: pd.DataFrame) -> Path:
        """Persist processed parquet files partitioned by symbol/timeframe."""
        path = self.processed_dir / symbol
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / f"{timeframe}.parquet"
        frame.to_parquet(file_path, index=False)
        return file_path

    def load_processed(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        """Read processed parquet if it exists."""
        file_path = self.processed_dir / symbol / f"{timeframe}.parquet"
        if not file_path.exists():
            return None
        return pd.read_parquet(file_path)

    def save_raw_csv(self, symbol: str, timeframe: str, rows: list[Dict[str, Any]]) -> Optional[Path]:
        """Persist raw rows as CSV for easier offline inspection."""
        if not rows:
            return None
        path = self.raw_dir / "csv" / symbol
        path.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(rows)
        file_path = path / f"{timeframe}.csv"
        df.to_csv(file_path, index=False, encoding="utf-8-sig")
        return file_path
