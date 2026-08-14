# Copyright (c) 2026 Lumine. All rights reserved.
"""Create users table (internal session auth).

Replaces the Authelia/Keycloak SSO stack with first-party session auth:
users live in PostgreSQL, credentials are PBKDF2-HMAC-SHA256 hashes with
per-user salts, and the API issues an HMAC-signed HttpOnly session cookie.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("username", sa.Text(), nullable=False, unique=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("password_salt", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Index("ix_users_username", "username"),
    )


def downgrade() -> None:
    op.drop_table("users")
