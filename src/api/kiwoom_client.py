"""Kiwoom REST API client abstraction."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.exceptions import (
    AuthenticationError,
    ConfigurationError,
    KiwoomAPIError,
    RateLimitError,
)
from src.core.logging_config import get_logger
from src.core.settings import AppSettings, get_settings
from src.services.notifier import ConsoleNotifier, NotificationLevel, Notifier


class KiwoomRESTClient:
    """Minimal Kiwoom REST API wrapper with retry and logging."""

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        logger: Optional[logging.Logger] = None,
        notifier: Optional[Notifier] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.logger = logger or get_logger("api.kiwoom")
        self.notifier = notifier or ConsoleNotifier(logger=self.logger)
        self.session = requests.Session()
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

        kiwoom_cfg = self.settings.kiwoom
        self.base_url: str = kiwoom_cfg.get("base_url", "")
        self.endpoints: Dict[str, str] = kiwoom_cfg.get("endpoints", {})
        self.default_headers: Dict[str, Any] = kiwoom_cfg.get("default_headers", {})

        if not self.base_url:
            raise ConfigurationError("Kiwoom base_url is missing in data_sources.yaml")

    def authenticate(self, force: bool = False) -> str:
        """Authenticate and cache access token."""
        if (
            self._access_token
            and self._token_expiry
            and self._token_expiry > datetime.now(timezone.utc) + timedelta(seconds=60)
            and not force
        ):
            return self._access_token

        creds = self.settings.credentials
        if not creds.app_sky or not creds.sec_key:
            raise ConfigurationError("app_sky/sec_key credentials are required.")

        endpoint = self.endpoints.get("authenticate")
        if not endpoint:
            raise ConfigurationError("authenticate endpoint missing in config.")

        payload = {
            "appkey": creds.app_sky,
            "appsecret": creds.sec_key,
        }

        try:
            response = self.session.post(
                urljoin(self.base_url, endpoint),
                json=payload,
                timeout=self.settings.rest_timeout,
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            self.logger.error("Authentication request failed: %s", exc)
            raise AuthenticationError("Kiwoom authentication failed") from exc

        access_token = body.get("access_token")
        expires_in = body.get("expires_in", 3600)
        if not access_token:
            raise AuthenticationError(f"Invalid authentication response: {body}")

        self._access_token = access_token
        self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.logger.info("Authenticated with Kiwoom REST API")
        return access_token

    def _build_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.authenticate()}",
            "Content-Type": "application/json",
        }
        headers.update(self.default_headers)
        if extra:
            headers.update(extra)
        return headers

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        include_auth: bool = True,
    ) -> Dict[str, Any]:
        if not endpoint:
            raise ConfigurationError("Endpoint path is required.")

        url = urljoin(self.base_url, endpoint)
        req_headers = self._build_headers(headers) if include_auth else headers or {}

        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_payload,
                headers=req_headers,
                timeout=self.settings.rest_timeout,
            )
        except requests.RequestException as exc:
            self.logger.error("Network error calling Kiwoom API: %s", exc)
            raise KiwoomAPIError("Network error") from exc

        if response.status_code == 429:
            raise RateLimitError("Kiwoom API rate limit reached.")

        if not response.ok:
            message = f"Kiwoom API error {response.status_code}: {response.text}"
            self.logger.error(message)
            self.notifier.notify(
                "Kiwoom API error",
                level=NotificationLevel.ERROR,
                payload={"status": response.status_code, "body": response.text},
            )
            raise KiwoomAPIError(message)

        try:
            return response.json()
        except ValueError as exc:
            raise KiwoomAPIError("Failed to parse JSON response") from exc

    def get_candles(self, symbol: str, timeframe: str, count: int = 200) -> Dict[str, Any]:
        """Fetch candle data for a symbol."""
        endpoint = self.endpoints.get("candles")
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol, "fid_input_hour_1": timeframe, "count": count}
        return self._request("GET", endpoint, params=params)

    def get_supply_data(self, symbol: str) -> Dict[str, Any]:
        """Fetch investor supply data."""
        endpoint = self.endpoints.get("supply")
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol}
        return self._request("GET", endpoint, params=params)

    def get_market_index(self, index_code: str) -> Dict[str, Any]:
        """Fetch market index information."""
        endpoint = self.endpoints.get("market_index") or self.endpoints.get("candles")
        params = {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": index_code}
        return self._request("GET", endpoint, params=params)

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        price: Optional[float] = None,
        order_type: str = "00",
    ) -> Dict[str, Any]:
        """Submit an order via the Kiwoom REST endpoint."""
        endpoint = self.endpoints.get("order")
        account = "".join(ch for ch in self.settings.credentials.account_no if ch.isdigit())
        if len(account) < 10:
            raise ConfigurationError("ACCOUNT_NO must include at least 10 digits (e.g., 12345678-01).")
        cano, product_code = account[:8], account[8:10]
        payload = {
            "CANO": cano,
            "ACNT_PRDT_CD": product_code,
            "PDNO": symbol,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price or 0),
            "ORD_DVSN_CD": side.upper(),
        }
        response = self._request("POST", endpoint, json_payload=payload)
        self.logger.info("Order submitted", extra={"symbol": symbol, "side": side, "qty": quantity})
        return response
