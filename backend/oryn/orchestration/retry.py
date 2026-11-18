from datetime import timedelta

from temporalio.common import RetryPolicy

AGENT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=4,
    non_retryable_error_types=["NonRetryable"],
)
ACTION_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=6,
    non_retryable_error_types=["NonRetryable"],
)
QUICK_RETRY = RetryPolicy(initial_interval=timedelta(milliseconds=500), maximum_attempts=10)

AGENT_START_TO_CLOSE = timedelta(seconds=180)
ACTION_START_TO_CLOSE = timedelta(seconds=60)
QUICK_START_TO_CLOSE = timedelta(seconds=30)
HEARTBEAT = timedelta(seconds=60)
