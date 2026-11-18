import asyncio
import random

from oryn.connectors.errors import RetryableConnectorError


class FaultInjector:
    """Simulates an unreliable outside world so retries and recovery are visible in demos."""

    def __init__(
        self,
        failure_rate: float,
        latency_ms: int,
        rng: random.Random | None = None,
        fail_attempts: int = 0,
        attempt: int = 1,
    ) -> None:
        self.failure_rate = max(0.0, min(1.0, failure_rate))
        self.latency_ms = max(0, latency_ms)
        self.rng = rng or random.Random()
        # Deterministic outage: every call fails while the activity attempt is <= fail_attempts.
        self.fail_attempts = max(0, fail_attempts)
        self.attempt = attempt

    async def maybe_fail(self, op: str) -> None:
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)
        if self.attempt <= self.fail_attempts:
            raise RetryableConnectorError(
                f"sandbox: simulated outage in {op} (attempt {self.attempt})", provider="sandbox"
            )
        if self.failure_rate and self.rng.random() < self.failure_rate:
            raise RetryableConnectorError(f"sandbox: injected transient failure in {op}", provider="sandbox")
