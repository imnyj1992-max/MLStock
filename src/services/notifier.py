"""Notification helpers for system events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import logging
from typing import Any, Dict, Optional

import requests


class NotificationLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Notifier:
    """Base notifier interface."""

    def notify(
        self,
        message: str,
        *,
        level: NotificationLevel = NotificationLevel.INFO,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        raise NotImplementedError


@dataclass
class ConsoleNotifier(Notifier):
    """Simple notifier that logs messages to stdout."""

    logger: logging.Logger

    def notify(
        self,
        message: str,
        *,
        level: NotificationLevel = NotificationLevel.INFO,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        text = message
        if payload:
            text = f"{message} | {json.dumps(payload, ensure_ascii=False)}"
        self.logger.log(getattr(logging, level.value, logging.INFO), text)


@dataclass
class WebhookNotifier(Notifier):
    """Send notifications to a webhook endpoint."""

    url: str
    session: requests.Session
    logger: logging.Logger

    def notify(
        self,
        message: str,
        *,
        level: NotificationLevel = NotificationLevel.INFO,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        data = {"message": message, "level": level.value, "payload": payload or {}}
        try:
            response = self.session.post(self.url, json=data, timeout=5)
            response.raise_for_status()
        except requests.RequestException as exc:
            self.logger.warning("Webhook notification failed: %s", exc)
