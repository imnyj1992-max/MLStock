"""Application entrypoint (Phase 0 bootstrap)."""

from __future__ import annotations

import sys

from src.api.kiwoom_client import KiwoomRESTClient
from src.core.exceptions import ConfigurationError
from src.core.logging_config import configure_logging, get_logger
from src.core.settings import get_settings
from src.data_pipeline.collectors.candle_collector import CandleCollector
from src.services.notifier import ConsoleNotifier


def bootstrap() -> None:
    logger = configure_logging()
    settings = get_settings()
    logger.info("Starting MLStock Phase 0 bootstrap", extra={"mode": settings.mode})

    notifier = ConsoleNotifier(logger=logger)
    try:
        client = KiwoomRESTClient(settings=settings, logger=get_logger("api"), notifier=notifier)
    except ConfigurationError as exc:
        logger.error("Failed to initialize Kiwoom client: %s", exc)
        sys.exit(1)

    collector = CandleCollector(client=client, timeframe="1m", count=10)

    # Phase 0 smoke test (does not place orders, only validates configuration flow).
    try:
        credentials_masked = settings.credentials.masked()
        logger.info("Loaded credentials", extra=credentials_masked)
        # Actual API call should be mocked/offline until credentials provided.
        logger.info("Phase 0 ready - GUI layer will trigger collectors and trading workflows.")
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Bootstrap failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    bootstrap()
