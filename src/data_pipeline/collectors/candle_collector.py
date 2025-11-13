"""Collector for pulling candle data via Kiwoom REST."""

from __future__ import annotations

from typing import Any, Dict, List

from src.api.kiwoom_client import KiwoomRESTClient
from src.data_pipeline.collectors.base_collector import BaseCollector


class CandleCollector(BaseCollector):
    """Fetches candle data for configured symbols/timeframes."""

    MARKET_TIMEFRAMES = {"day", "1d", "daily"}

    def __init__(self, client: KiwoomRESTClient | None = None, *, timeframe: str = "1m", count: int = 200):
        super().__init__(client)
        self.timeframe = timeframe
        self.count = count
        self.use_market_api = timeframe.lower() in self.MARKET_TIMEFRAMES

    def run(self, symbol: str) -> Dict[str, Any]:
        self.logger.info("Collecting candles", extra={"symbol": symbol, "timeframe": self.timeframe})
        if self.use_market_api:
            body, _ = self.client.get_market_condition(symbol=symbol)
            num_rows = len(body.get("stk_ddwkmm", []))
            self.logger.info("Collected market data", extra={"symbol": symbol, "rows": num_rows})
            return body
        response, _ = self.client.get_candles(symbol=symbol, timeframe=self.timeframe, count=self.count)
        num_rows = len(response.get("output", []))
        self.logger.info("Collected candles", extra={"symbol": symbol, "rows": num_rows})
        return response

    def run_full_history(self, symbol: str, *, max_pages: int = 200) -> Dict[str, Any]:
        """Collect candles across all available pages using cont-yn headers."""
        self.logger.info("Collecting full history", extra={"symbol": symbol, "timeframe": self.timeframe})
        aggregated: List[Dict[str, Any]] = []
        cont_flag = "N"
        next_key = ""
        for _ in range(max_pages):
            if self.use_market_api:
                body, headers = self.client.get_market_condition(symbol=symbol, cont_yn=cont_flag, next_key=next_key)
                aggregated.extend(body.get("stk_ddwkmm", []))
            else:
                body, headers = self.client.get_candles(
                    symbol=symbol,
                    timeframe=self.timeframe,
                    count=self.count,
                    cont_yn=cont_flag,
                    next_key=next_key,
                )
                aggregated.extend(body.get("output", []))
            next_key = headers.get("next-key") or headers.get("Next-Key") or ""
            cont_flag = (headers.get("cont-yn") or headers.get("Cont-Yn") or "N").upper()
            if cont_flag != "Y" or not next_key:
                break
        else:
            self.logger.warning("Reached pagination limit", extra={"symbol": symbol, "timeframe": self.timeframe})

        self.logger.info(
            "Collected full history",
            extra={"symbol": symbol, "timeframe": self.timeframe, "rows": len(aggregated)},
        )
        if self.use_market_api:
            return {"stk_ddwkmm": aggregated}
        return {"output": aggregated}
