"""Abstract collector definitions for market data ingestion."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.api.kiwoom_client import KiwoomRESTClient
from src.core.logging_config import get_logger


class BaseCollector:
    """Base class for data collectors."""

    def __init__(self, client: Optional[KiwoomRESTClient] = None, logger: Optional[logging.Logger] = None) -> None:
        self.client = client or KiwoomRESTClient()
        self.logger = logger or get_logger(self.__class__.__name__)

    def run(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Entrypoint for collectors."""
        raise NotImplementedError
