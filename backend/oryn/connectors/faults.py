import asyncio
import random

from oryn.connectors.errors import RetryableConnectorError


class FaultInjector:
    """Simulates an unreliable outside world so retries and recovery are visible in demos."""

    def __init__(self, failure_rate: float, latency_ms: int, rng: random.Random | None = None) -> None:
        self.failure_rate = max(0.0, min(1.0, failure_rate))
        self.latency_ms = max(0, latency_ms)
        self.rng = rng or random.Random()

    async def maybe_fail(self, op: str) -> None:
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)
        if self.failure_rate and self.rng.random() < self.failure_rate:
            raise RetryableConnectorError(f"sandbox: injected transient failure in {op}", provider="sandbox")
