"""python -m oryn.seed [--no-backfill] [--days N]"""

import argparse
import asyncio

from oryn.core.logging import configure_logging, log
from oryn.orchestration.client import get_temporal_client
from oryn.seed.backfill import backfill
from oryn.seed.fixtures import seed_base


async def main() -> None:
    p = argparse.ArgumentParser(description="Seed Oryn OS demo data")
    p.add_argument("--no-backfill", action="store_true")
    p.add_argument("--days", type=int, default=14)
    args = p.parse_args()
    configure_logging()
    summary = await seed_base()
    log.info("seed.base", tenants=[t.slug for t in summary.tenants], created=summary.created)
    if args.no_backfill or not summary.created:
        log.info("seed.backfill_skipped", reason="flag" if args.no_backfill else "tenants already existed")
        return
    result = await backfill(await get_temporal_client(), days=args.days, tenants=summary.created)
    log.info("seed.backfill_done", runs=result.runs_started, approvals_decided=result.approvals_decided)


if __name__ == "__main__":
    asyncio.run(main())
