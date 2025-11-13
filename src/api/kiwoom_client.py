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
        self._closed = False

        kiwoom_cfg = self.settings.kiwoom
        self.base_url: str = self._resolve_base_url(kiwoom_cfg)
        self.endpoints: Dict[str, str] = kiwoom_cfg.get("endpoints", {})
        self.default_headers: Dict[str, Any] = self._normalize_headers(kiwoom_cfg.get("default_headers", {}))

        if not self.base_url:
            raise ConfigurationError("Kiwoom base_url is missing in data_sources.yaml")

    @property
    def token_expiry(self) -> Optional[datetime]:
        """Expose current token expiry (read-only)."""
        return self._token_expiry

    def update_credentials(self, *, app_sky: str, sec_key: str, account_no: str) -> None:
        """Update credentials at runtime (e.g., from GUI input)."""
        self.settings.credentials.app_sky = app_sky.strip()
        self.settings.credentials.sec_key = sec_key.strip()
        self.settings.credentials.account_no = account_no.strip()
        # Force token refresh on next request.
        self._access_token = None
        self._token_expiry = None

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
            "grant_type": "client_credentials",
            "appkey": creds.app_sky,
            "secretkey": creds.sec_key,
        }

        try:
            response = self.session.post(
                urljoin(self.base_url, endpoint),
                json=payload,
                headers={"Content-Type": "application/json;charset=UTF-8"},
                timeout=self.settings.rest_timeout,
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            self.logger.error("Authentication request failed: %s", exc)
            raise AuthenticationError("Kiwoom authentication failed") from exc

        access_token = body.get("access_token") or body.get("token")
        if not access_token:
            return_code = str(body.get("return_code"))
            if return_code and return_code != "0":
                raise AuthenticationError(body.get("return_msg") or f"Authentication failed: {body}")
            raise AuthenticationError(f"Invalid authentication response: {body}")

        expires_in = self._resolve_expiry(body)

        self._access_token = access_token
        self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.logger.info(
            "Authenticated with Kiwoom REST API",
            extra={"token_type": body.get("token_type"), "expires_in": expires_in},
        )
        return access_token

    def _normalize_headers(self, headers: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize header keys for consistency."""
        normalized: Dict[str, Any] = {}
        headers = headers or {}
        for key, value in headers.items():
            if not key:
                continue
            header_key = key.strip()
            lower = header_key.lower()
            if lower in {"content_type", "content-type"}:
                header_key = "Content-Type"
            normalized[header_key] = value

        normalized.setdefault("Content-Type", "application/json;charset=UTF-8")
        return normalized

    def _resolve_base_url(self, config: Dict[str, Any]) -> str:
        """Resolve base URL considering paper/live hosts and legacy fields."""

        env_key = "live" if self.settings.is_live else "paper"

        def pick(value: Any) -> Optional[str]:
            if isinstance(value, dict):
                return value.get(env_key) or value.get("paper") or value.get("live")
            if isinstance(value, str):
                return value
            return None

        candidates = [
            pick(config.get("base_url")),
            pick(config.get("hosts")),
        ]
        base_config = config.get("base_url")
        if isinstance(base_config, str):
            candidates.append(base_config)

        for url in candidates:
            if url:
                return url

        # Hard-coded fallback to ensure GUI can boot even if config is missing.
        return "https://api.kiwoom.com" if self.settings.is_live else "https://mockapi.kiwoom.com"

    def _build_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.authenticate()}",
            "Content-Type": "application/json;charset=UTF-8",
        }
        headers.update(self.default_headers)
        if extra:
            headers.update(extra)
        return headers

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
        body, _ = self._request_with_headers(
            method,
            endpoint,
            params=params,
            json_payload=json_payload,
            headers=headers,
            include_auth=include_auth,
        )
        return body

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    def _request_with_headers(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        include_auth: bool = True,
    ) -> tuple[Dict[str, Any], requests.structures.CaseInsensitiveDict[str]]:
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
            raise KiwoomAPIError(message, status_code=response.status_code, payload=response.text)

        try:
            return response.json(), response.headers
        except ValueError as exc:
            raise KiwoomAPIError("Failed to parse JSON response", payload=response.text) from exc

    def _split_account(self) -> tuple[str, str]:
        digits = "".join(ch for ch in self.settings.credentials.account_no if ch.isdigit())
        if len(digits) < 8:
            raise ConfigurationError("ACCOUNT_NO must include at least 8 digits (e.g., 12345678-01).")
        if len(digits) == 8:
            return digits, "01"
        if len(digits) == 9:
            return digits[:8], digits[8:].rjust(2, "0")
        return digits[:8], digits[8:10]

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
        *,
        cont_yn: str = "N",
        next_key: str = "",
    ) -> tuple[Dict[str, Any], requests.structures.CaseInsensitiveDict[str]]:
        """Fetch candle data for a symbol, supporting pagination headers."""
        endpoint = self.endpoints.get("candles")
        tf_code, tr_id = self._resolve_timeframe(timeframe)
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol, "count": count}
        if tf_code:
            params["fid_input_hour_1"] = tf_code
        headers = {"tr_id": tr_id}
        if cont_yn == "Y" or next_key:
            headers["cont-yn"] = cont_yn
            if next_key:
                headers["next-key"] = next_key
        return self._request_with_headers("GET", endpoint, params=params, headers=headers)

    def get_market_condition(
        self,
        *,
        symbol: str,
        payload: Optional[Dict[str, Any]] = None,
        cont_yn: str = "N",
        next_key: str = "",
    ) -> tuple[Dict[str, Any], requests.structures.CaseInsensitiveDict[str]]:
        endpoint = self.endpoints.get("market_condition")
        if not endpoint:
            raise ConfigurationError("market_condition endpoint missing in data_sources.yaml")
        api_id = self.settings.kiwoom.get("market_condition_api_id", "ka10005")
        body = payload.copy() if payload else {"stk_cd": symbol}
        headers = {"api-id": api_id}
        if cont_yn == "Y" or next_key:
            headers["cont-yn"] = cont_yn
            if next_key:
                headers["next-key"] = next_key
        return self._request_with_headers("POST", endpoint, json_payload=body, headers=headers)

    @staticmethod
    def _resolve_timeframe(timeframe: str) -> tuple[Optional[str], str]:
        tf = timeframe.lower()
        minute_map = {
            "1m": "1",
            "3m": "3",
            "5m": "5",
            "10m": "10",
            "15m": "15",
            "30m": "30",
            "60m": "60",
            "1h": "60",
            "2h": "120",
            "4h": "240",
            "6h": "360",
        }
        if tf in ("tick", "t"):
            return None, "FHKST03010200"
        if tf in minute_map:
            return minute_map[tf], "FHKST03010200"
        return None, "HHDFS00000300"

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
        cano, product_code = self._split_account()
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

    def get_account_overview(self, *, qry_type: str = "0", market: str = "KRX") -> Dict[str, Any]:
        """Retrieve account evaluation overview with pagination support."""
        endpoint = self.endpoints.get("account_overview") or self.endpoints.get("balance")
        if not endpoint:
            raise ConfigurationError("account_overview endpoint missing.")

        cano, product_code = self._split_account()
        api_id = self.settings.kiwoom.get("account_overview_api_id", "kt00004")
        cont_flag = "N"
        next_key = ""
        aggregated_holdings: list[Dict[str, Any]] = []
        summaries: list[Dict[str, Any]] = []
        raw_pages: list[Dict[str, Any]] = []

        for _ in range(50):  # safety guard
            payload = {
                "cano": cano,
                "acnt_prdt_cd": product_code,
                "qry_tp": qry_type,
                "dmst_stex_tp": market,
            }
            headers = {"api-id": api_id, "cont-yn": cont_flag, "next-key": next_key}
            body, resp_headers = self._request_with_headers(
                "POST",
                endpoint,
                json_payload=payload,
                headers=headers,
            )
            raw_pages.append(body)

            holdings = body.get("output1") or body.get("output") or body.get("stk_acnt_evlt_prst") or []
            summary = body.get("output2") or body.get("summary") or []

            if isinstance(holdings, list):
                aggregated_holdings.extend(holdings)

            if isinstance(summary, list):
                summaries.extend(summary)
            elif summary:
                summaries.append(summary)

            cont_header = (resp_headers.get("cont-yn") or resp_headers.get("Cont-Yn") or "N").upper()
            next_key = resp_headers.get("next-key") or resp_headers.get("Next-Key") or ""
            if cont_header != "Y" or not next_key:
                break
            cont_flag = "Y"
        else:
            self.logger.warning("Account overview pagination limit reached")

        self.logger.info("Fetching account overview", extra={"account": f"{cano}-{product_code}", "pages": len(raw_pages)})
        return {
            "output1": aggregated_holdings,
            "output2": summaries,
            "raw_pages": raw_pages,
            "next_key": next_key,
        }

    @staticmethod
    def _resolve_expiry(body: Dict[str, Any]) -> int:
        """Determine token expiration seconds from multiple Kiwoom response formats."""
        expires_in = body.get("expires_in")
        if isinstance(expires_in, (int, float)):
            return int(expires_in)
        if isinstance(expires_in, str) and expires_in.isdigit():
            return int(expires_in)

        expires_dt = body.get("expires_dt")
        if expires_dt:
            try:
                expiry = datetime.strptime(expires_dt, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                delta = expiry - datetime.now(timezone.utc)
                return max(int(delta.total_seconds()), 0)
            except ValueError:
                pass

        return 3600

    def revoke_token(self) -> None:
        """Invalidate the current access token if Kiwoom provides a logout endpoint."""
        if not self._access_token:
            return

        endpoint = self.endpoints.get("logout")
        if endpoint:
            try:
                self.session.post(
                    urljoin(self.base_url, endpoint),
                    headers={"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"},
                    timeout=self.settings.rest_timeout,
                )
                self.logger.info("Revoked Kiwoom REST token")
            except requests.RequestException as exc:
                self.logger.warning("Failed to revoke token: %s", exc)

        self._access_token = None
        self._token_expiry = None

    def close(self) -> None:
        """Revoke token and close HTTP session."""
        if self._closed:
            return
        self.revoke_token()
        self.session.close()
        self._closed = True

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # pragma: no cover
            pass
