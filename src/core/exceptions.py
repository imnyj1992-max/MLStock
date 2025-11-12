"""Custom exception hierarchy for the MLStock project."""


class MLStockError(Exception):
    """Base exception for MLStock."""


class ConfigurationError(MLStockError):
    """Raised when required configuration or credentials are missing."""


class AuthenticationError(MLStockError):
    """Raised when authentication against Kiwoom REST API fails."""


class RateLimitError(MLStockError):
    """Raised when the upstream API responds with a rate-limit error."""


class KiwoomAPIError(MLStockError):
    """Raised for non-success Kiwoom REST API responses."""
