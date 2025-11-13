"""Manage symbol metadata and search functionality."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

from src.core.logging_config import get_logger
from src.core.settings import get_settings


@dataclass
class SymbolRecord:
    symbol: str
    name: str
    market: str
    listing_date: datetime


class SymbolRegistry:
    """Loads symbol metadata from CSV and provides search utilities."""

    def __init__(self, csv_path: Optional[Path] = None) -> None:
        settings = get_settings()
        default_path = settings.paths.root / "data" / "symbols" / "symbols.csv"
        self.csv_path = csv_path or default_path
        self.logger = get_logger("symbols.registry")
        self._frame = self._load()

    def _load(self) -> pd.DataFrame:
        if not self.csv_path.exists():
            self.logger.warning("Symbol CSV not found at %s. Creating a placeholder.", self.csv_path)
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            sample = pd.DataFrame(
                [
                    {"symbol": "005930", "name": "삼성전자", "market": "KRX", "listing_date": "1975-06-11"},
                    {"symbol": "000660", "name": "SK하이닉스", "market": "KRX", "listing_date": "1996-12-26"},
                    {"symbol": "035420", "name": "NAVER", "market": "KRX", "listing_date": "2008-11-28"},
                ]
            )
            sample["listing_date"] = pd.to_datetime(sample["listing_date"])
            sample.to_csv(self.csv_path, index=False, encoding="utf-8")
            return sample

        frame = pd.read_csv(self.csv_path, dtype=str)
        frame["listing_date"] = pd.to_datetime(frame["listing_date"])
        return frame

    def search(self, keyword: str, *, market: Optional[str] = None, limit: int = 20) -> List[SymbolRecord]:
        frame = self._frame
        if market:
            frame = frame[frame["market"].str.lower() == market.lower()]
        mask = frame["symbol"].str.contains(keyword) | frame["name"].str.contains(keyword, case=False)
        results = frame[mask].head(limit)
        return [
            SymbolRecord(
                symbol=row["symbol"],
                name=row["name"],
                market=row["market"],
                listing_date=pd.to_datetime(row["listing_date"]),
            )
            for _, row in results.iterrows()
        ]

    def get(self, symbol: str) -> Optional[SymbolRecord]:
        row = self._frame[self._frame["symbol"] == symbol].head(1)
        if row.empty:
            return None
        rec = row.iloc[0]
        return SymbolRecord(
            symbol=rec["symbol"],
            name=rec["name"],
            market=rec["market"],
            listing_date=pd.to_datetime(rec["listing_date"]),
        )

    def add_or_update(self, records: Iterable[SymbolRecord]) -> None:
        frame = self._frame.copy()
        for record in records:
            frame = frame[frame["symbol"] != record.symbol]
            frame = pd.concat(
                [
                    frame,
                    pd.DataFrame(
                        {
                            "symbol": [record.symbol],
                            "name": [record.name],
                            "market": [record.market],
                            "listing_date": [record.listing_date.strftime("%Y-%m-%d")],
                        }
                    ),
                ],
                ignore_index=True,
            )
        frame.sort_values("symbol", inplace=True)
        frame.to_csv(self.csv_path, index=False, encoding="utf-8")
        self._frame = frame
