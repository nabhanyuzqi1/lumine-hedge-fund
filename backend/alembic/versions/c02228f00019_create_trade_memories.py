"""create trade_memories table

Revision ID: c02228f00019
Revises: c02228f00018
Create Date: 2026-08-21 23:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c02228f00019'
down_revision: Union[str, None] = 'c02228f00018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # P2 (21 Aug 2026): persistent trade memory — pengalaman trading nyata
    # (bukan backtest) yang di-replay ke prompt LLM per cycle. Satu baris =
    # satu posisi tertutup: konteks keputusan (side/conf/reason), hasil
    # (pnl/pips/durasi), dan pelajaran singkat.
    op.create_table(
        "trade_memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("position_id", sa.String(length=64), nullable=False),
        sa.Column("mt5_ticket", sa.BigInteger(), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("volume", sa.Numeric(18, 8), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 8), nullable=False),
        sa.Column("exit_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("sl", sa.Numeric(18, 8), nullable=True),
        sa.Column("tp", sa.Numeric(18, 8), nullable=True),
        sa.Column("profit_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("pips", sa.Numeric(12, 1), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_reason", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("profile_id", sa.String(length=40), nullable=True),
        sa.Column("lesson", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("digest_included", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(
        "ix_trade_memories_closed_at",
        "trade_memories",
        ["closed_at"],
    )
    op.create_index(
        "ix_trade_memories_symbol_side",
        "trade_memories",
        ["symbol", "side"],
    )


def downgrade() -> None:
    op.drop_index("ix_trade_memories_symbol_side", table_name="trade_memories")
    op.drop_index("ix_trade_memories_closed_at", table_name="trade_memories")
    op.drop_table("trade_memories")
