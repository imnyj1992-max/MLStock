"""Collector for pulling candle data via Kiwoom REST."""

from __future__ import annotations

from typing import Any, Dict

from src.api.kiwoom_client import KiwoomRESTClient
from src.data_pipeline.collectors.base_collector import BaseCollector


class CandleCollector(BaseCollector):
    """Fetches candle data for configured symbols/timeframes."""

    def __init__(self, client: KiwoomRESTClient | None = None, *, timeframe: str = "1m", count: int = 200):
        super().__init__(client)
        self.timeframe = timeframe
        self.count = count

    def run(self, symbol: str) -> Dict[str, Any]:
        self.logger.info("Collecting candles", extra={"symbol": symbol, "timeframe": self.timeframe})
        response = self.client.get_candles(symbol=symbol, timeframe=self.timeframe, count=self.count)
        num_rows = len(response.get("output", []))
        self.logger.info("Collected candles", extra={"symbol": symbol, "rows": num_rows})
        return response
