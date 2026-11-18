import random
from datetime import UTC, datetime

import pytest

from oryn.connectors.faults import FaultInjector
from oryn.core.db import tenant_session
from tests.factories import make_tenant

# A fixed "now": Monday 2026-11-16 08:00 America/New_York (13:00 UTC).
FIXED_NOW = datetime(2026, 11, 16, 13, 0, tzinfo=UTC)


@pytest.fixture
async def tenant():
    return await make_tenant("acme", timezone="America/New_York")


@pytest.fixture
def no_faults() -> FaultInjector:
    return FaultInjector(0.0, 0, random.Random(1))


@pytest.fixture
async def session(tenant):
    async with tenant_session(tenant.id) as s:
        yield s
