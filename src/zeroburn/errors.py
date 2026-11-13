"""ZeroBurn error hierarchy."""
from __future__ import annotations


class ZeroBurnError(Exception):
    """Base exception for all ZeroBurn errors."""
    pass


class RateLimited(ZeroBurnError):
    """Raised when an upstream provider or gateway rate-limits a request (HTTP 429)."""
    pass


class ProviderDown(ZeroBurnError):
    """Raised on upstream 5xx, timeouts, or connection failures."""
    pass


class BudgetBlocked(ZeroBurnError):
    """Raised when the gateway blocks a request due to gateway-side budget limits."""
    pass


class GatewayPolicyBlocked(ZeroBurnError):
    """Raised when gateway policy rejects a provider/model (e.g. cloud model on confidential key)."""
    pass


class BadRequest(ZeroBurnError):
    """Raised when gateway returns HTTP 400 invalid request."""
    pass


class AuthError(ZeroBurnError):
    """Raised on HTTP 401 authentication error."""
    pass


class PolicyViolation(ZeroBurnError):
    """Raised when local policy is violated (e.g., cloud model planned for confidential repo or path escape)."""
    pass


class ApprovalDenied(ZeroBurnError):
    """Raised when human user denies an action approval request."""
    pass


class BudgetExhausted(ZeroBurnError):
    """Raised when local budget limit is exhausted and policy is set to stop."""
    pass
