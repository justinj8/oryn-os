import pytest

from oryn.connectors.errors import (
    ConnectorError,
    ErrorClass,
    NonRetryableConnectorError,
    RetryableConnectorError,
    classify_error,
)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (RetryableConnectorError("x"), ErrorClass.retryable),
        (NonRetryableConnectorError("x"), ErrorClass.non_retryable),
        (ConnectorError("x", status_code=429), ErrorClass.rate_limited),
        (ConnectorError("x", status_code=503), ErrorClass.retryable),
        (ConnectorError("x", status_code=408), ErrorClass.retryable),
        (ConnectorError("x", status_code=404), ErrorClass.non_retryable),
        (TimeoutError(), ErrorClass.retryable),
        (ConnectionError(), ErrorClass.retryable),
        (ValueError(), ErrorClass.non_retryable),
        (RuntimeError(), ErrorClass.retryable),
    ],
)
def test_classify_error(exc: BaseException, expected: ErrorClass) -> None:
    assert classify_error(exc) is expected


def test_explicit_subclass_beats_status_code() -> None:
    assert classify_error(NonRetryableConnectorError("x", status_code=503)) is ErrorClass.non_retryable
