"""warehouse role for agent-supplied SQL

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The business data agents may query (RLS still restricts every row to the current tenant).
WAREHOUSE_TABLES = (
    "sb_contacts",
    "sb_deals",
    "sb_calendar_events",
    "sb_messages",
    "sb_invoices",
    "sb_tickets",
    "sb_documents",
)


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'oryn_warehouse') THEN
            RAISE EXCEPTION 'role oryn_warehouse is missing: recreate the database volume (make down -v) '
                            'so deploy/postgres/init.sql runs';
          END IF;
        END $$""")
    for table in WAREHOUSE_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO oryn_warehouse")


def downgrade() -> None:
    for table in WAREHOUSE_TABLES:
        op.execute(f"REVOKE SELECT ON {table} FROM oryn_warehouse")
