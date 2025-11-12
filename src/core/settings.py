"""Centralized application settings and configuration loaders."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Credentials(BaseModel):
    """Holds Kiwoom credential values."""

    app_sky: str = Field(default="", description="Kiwoom REST app key (app_sky).")
    sec_key: str = Field(default="", description="Kiwoom REST secret key (sec_key).")
    account_no: str = Field(default="", description="Primary trading account number.")

    def masked(self) -> Dict[str, str]:
        """Return a masked representation safe for logging."""
        return {
            "app_sky": f"{self.app_sky[:3]}***" if self.app_sky else "",
            "sec_key": f"{self.sec_key[:3]}***" if self.sec_key else "",
            "account_no": f"{self.account_no[:3]}****" if self.account_no else "",
        }


class PathSettings(BaseModel):
    """Common filesystem locations."""

    root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1])
    config_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "configs")
    log_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "logs" / "app")


class AppSettings(BaseModel):
    """Primary application configuration container."""

    mode: str = Field(default="paper", description="Trading mode: paper or live.")
    rest_timeout: float = Field(default=5.0, description="Default REST timeout in seconds.")
    credentials: Credentials = Field(default_factory=Credentials)
    data_sources: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, Any] = Field(default_factory=dict)
    risk: Dict[str, Any] = Field(default_factory=dict)
    paths: PathSettings = Field(default_factory=PathSettings)

    @property
    def is_live(self) -> bool:
        """Return True if the application runs against a live account."""
        return self.mode.lower() == "live"

    @property
    def kiwoom(self) -> Dict[str, Any]:
        """Shortcut to Kiwoom-specific configuration."""
        return self.data_sources.get("kiwoom", {})


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Load and cache application settings."""
    load_dotenv()
    paths = PathSettings()

    credentials = Credentials(
        app_sky=os.getenv("KIWOOM_APP_SKY") or os.getenv("KIWOOM_APP_KEY", ""),
        sec_key=os.getenv("KIWOOM_SEC_KEY") or os.getenv("KIWOOM_APP_SECRET", ""),
        account_no=os.getenv("KIWOOM_ACCOUNT_NO", ""),
    )

    data_sources = _load_yaml(paths.config_dir / "data_sources.yaml")
    features = _load_yaml(paths.config_dir / "features.yaml")
    risk = _load_yaml(paths.config_dir / "risk.yaml")

    return AppSettings(
        mode=os.getenv("MODE", "paper"),
        rest_timeout=float(os.getenv("REST_TIMEOUT", 5)),
        credentials=credentials,
        data_sources=data_sources,
        features=features,
        risk=risk,
        paths=paths,
    )
