"""Connector errors and the retry-classification decision.

``classify_error`` is the single place that decides how the platform reacts to a failure
from the outside world. Temporal retry policies, the agent loop and the MCP server all
route through it, so "is this worth retrying?" has exactly one answer.
"""

from enum import StrEnum

import httpx
import pydantic


class ErrorClass(StrEnum):
    retryable = "retryable"
    non_retryable = "non_retryable"
    rate_limited = "rate_limited"


class ConnectorError(Exception):
    def __init__(self, message: str, *, provider: str = "unknown", status_code: int | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class RetryableConnectorError(ConnectorError):
    """Transient: timeouts, 5xx, dropped connections. Safe to try again."""


class NonRetryableConnectorError(ConnectorError):
    """Permanent: bad input, business-rule violation, missing record. Retrying cannot help."""


def classify_error(exc: BaseException) -> ErrorClass:
    """Decide whether a failure should be retried.

    Order matters:
    1. An explicit Retryable/NonRetryable subclass is the connector author's statement of
       intent and always wins (a 503 that the author knows is permanent stays permanent).
    2. HTTP semantics: 429 → back off longer (rate_limited); 408 and 5xx → transient;
       any other 4xx → the request itself is wrong, so retrying is pointless.
    3. Network-level failures (timeouts, refused/reset connections) → transient.
    4. Validation and value errors → our input is wrong → permanent.
    5. Anything unrecognised → retryable. This is deliberate: every side-effecting call in
       Oryn carries an idempotency key, so a retry can never double-apply an action, while
       wrongly giving up on a transient failure would drop real work on the floor.
    """
    if isinstance(exc, NonRetryableConnectorError):
        return ErrorClass.non_retryable
    if isinstance(exc, RetryableConnectorError):
        return ErrorClass.retryable
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status == 429:
            return ErrorClass.rate_limited
        if status == 408 or status >= 500:
            return ErrorClass.retryable
        if 400 <= status < 500:
            return ErrorClass.non_retryable
    if isinstance(exc, TimeoutError | ConnectionError | httpx.TransportError):
        return ErrorClass.retryable
    if isinstance(exc, ValueError | TypeError | KeyError | pydantic.ValidationError):
        return ErrorClass.non_retryable
    return ErrorClass.retryable
