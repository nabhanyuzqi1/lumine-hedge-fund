"""Add DEFAULT partitions as safety-net for time-series tables.

ticks, bars_1m, bars_5m are RANGE-partitioned on ts. Without a DEFAULT
partition, a tick arriving outside any pre-created child partition range
causes the insert to fail and halts the pipeline. The DEFAULT partition
catches out-of-range rows so ingest degrades (route to default + alert)
rather than crashing. Proactive partition creation is handled by the
runtime lifecycle module src/lumine/data/partitions.py (per migrations.md:
partition pre-creation is a runtime job, not a migration).

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # DEFAULT partitions for the three RANGE-partitioned time-series tables.
    # FOR VALUES IN (DEFAULT) catches any row not matching a child partition.
    op.execute("CREATE TABLE IF NOT EXISTS ticks_default PARTITION OF ticks DEFAULT")
    op.execute("CREATE TABLE IF NOT EXISTS bars_1m_default PARTITION OF bars_1m DEFAULT")
    op.execute("CREATE TABLE IF NOT EXISTS bars_5m_default PARTITION OF bars_5m DEFAULT")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bars_5m_default")
    op.execute("DROP TABLE IF EXISTS bars_1m_default")
    op.execute("DROP TABLE IF EXISTS ticks_default")
