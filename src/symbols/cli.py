"""Command line utilities for symbol search and watchlist updates."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import yaml

from src.core.settings import get_settings
from src.symbols.registry import SymbolRecord, SymbolRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search KRX symbols and manage watchlists.")
    sub = parser.add_subparsers(dest="command", required=True)

    search_cmd = sub.add_parser("search", help="Search symbols by keyword.")
    search_cmd.add_argument("--keyword", required=True)
    search_cmd.add_argument("--market", default=None)
    search_cmd.add_argument("--limit", type=int, default=20)
    search_cmd.add_argument("--add-to-watchlist", action="store_true")

    return parser.parse_args()


def add_to_watchlist(records: List[SymbolRecord]) -> None:
    settings = get_settings()
    watchlist_path = settings.paths.config_dir / "watchlist.yaml"
    watchlist_path.parent.mkdir(parents=True, exist_ok=True)
    if watchlist_path.exists():
        with watchlist_path.open("r", encoding="utf-8") as handle:
            watchlist = yaml.safe_load(handle) or {}
    else:
        watchlist = {}
    symbols = watchlist.get("symbols", [])
    for record in records:
        if record.symbol not in symbols:
            symbols.append(record.symbol)
    watchlist["symbols"] = symbols
    with watchlist_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(watchlist, handle, allow_unicode=True)
    print(f"Updated watchlist at {watchlist_path} with {len(records)} symbol(s).")


def main() -> None:
    args = parse_args()
    registry = SymbolRegistry()

    if args.command == "search":
        records = registry.search(args.keyword, market=args.market, limit=args.limit)
        for record in records:
            print(
                f"{record.symbol}\t{record.name}\t{record.market}\t{record.listing_date.date()}",
            )
        if args.add_to_watchlist and records:
            add_to_watchlist(records)


if __name__ == "__main__":
    main()
