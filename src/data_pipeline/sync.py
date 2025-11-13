"""CLI entrypoint for data synchronization (Phase 1)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.core.logging_config import configure_logging
from src.core.settings import get_settings
from src.data_pipeline.service import DataSyncConfig, DataSyncService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Kiwoom candles and build features.")
    parser.add_argument("--symbols", nargs="+", help="List of symbol codes (default from configs/watchlist.yaml).")
    parser.add_argument("--timeframes", nargs="+", help="Timeframes such as 1m 15m 1h")
    parser.add_argument("--count", type=int, default=None, help="Candles per request (default 200).")
    parser.add_argument("--full-history", action="store_true", help="Fetch entire history since listing date.")
    return parser.parse_args()


def load_watchlist(default_path: Path) -> tuple[list[str], list[str], int]:
    import yaml

    with default_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    symbols = data.get("symbols", [])
    timeframes = data.get("default_timeframes", [])
    count = data.get("max_candles_per_request", 200)
    return symbols, timeframes, count


def main() -> None:
    configure_logging()
    settings = get_settings()
    args = parse_args()

    watchlist_path = settings.paths.config_dir / "watchlist.yaml"
    default_symbols, default_timeframes, default_count = load_watchlist(watchlist_path)

    symbols = args.symbols or default_symbols
    timeframes = args.timeframes or default_timeframes
    count = args.count or default_count

    service = DataSyncService(settings=settings)
    summary = service.run(
        DataSyncConfig(
            symbols=symbols,
            timeframes=timeframes,
            candles_per_request=count,
            full_history=args.full_history,
        )
    )
    for entry in summary["synced"]:
        print(
            f"{entry['symbol']} {entry['timeframe']} -> rows={entry['rows']} raw={entry['raw_path']}",
        )


if __name__ == "__main__":
    main()
