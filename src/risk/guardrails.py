"""Risk management guardrails."""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.core.logging_config import get_logger
from src.core.settings import AppSettings, get_settings


class RiskGuardrails:
    """Evaluates risk constraints before orders are submitted."""

    def __init__(self, settings: AppSettings | None = None, logger: logging.Logger | None = None) -> None:
        self.settings = settings or get_settings()
        self.config: Dict[str, Any] = self.settings.risk
        self.logger = logger or get_logger("risk.guardrails")

    def validate_position_limit(self, positions_count: int) -> bool:
        limit = self.config.get("position_limits", {}).get("max_positions", 0)
        if limit and positions_count >= limit:
            self.logger.warning("Position limit reached", extra={"limit": limit, "positions": positions_count})
            return False
        return True

    def validate_drawdown(self, intraday_drawdown_pct: float) -> bool:
        limit = self.config.get("drawdown", {}).get("intraday_pct")
        if limit and intraday_drawdown_pct <= -abs(limit):
            self.logger.error("Drawdown limit exceeded", extra={"limit": limit, "value": intraday_drawdown_pct})
            return False
        return True

    def validate_order_frequency(self, seconds_since_last_order: float) -> bool:
        min_interval = self.config.get("cooldown", {}).get("order_seconds", 0)
        if min_interval and seconds_since_last_order < min_interval:
            self.logger.warning(
                "Order cooldown violation",
                extra={"cooldown": min_interval, "elapsed": seconds_since_last_order},
            )
            return False
        return True

    def is_order_allowed(
        self,
        *,
        positions_count: int,
        intraday_drawdown_pct: float,
        seconds_since_last_order: float,
    ) -> bool:
        """Aggregate validation used before placing orders."""
        checks = [
            self.validate_position_limit(positions_count),
            self.validate_drawdown(intraday_drawdown_pct),
            self.validate_order_frequency(seconds_since_last_order),
        ]
        return all(checks)
