from datetime import UTC, datetime, timedelta


class OffsetClock:
    """Wall clock shifted by a fixed offset. Seeded history uses a negative offset so runs
    executed today are recorded at their simulated time in the past."""

    def __init__(self, offset_seconds: float = 0.0) -> None:
        self.offset = timedelta(seconds=offset_seconds)

    def now(self) -> datetime:
        return datetime.now(UTC) + self.offset
