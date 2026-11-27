"""Skema v2.3 agent LLM (t_f2llm1, KEPUTUSAN_OWNER G1).

Perubahan:
- users.role: 'admin' | 'agent' | 'user' (default 'admin' untuk baris lama).
  Service agent (fund2-llm-agent) memakai role 'agent': boleh POST /orders
  (tetap melewati risk gate), TIDAK boleh kill-switch/triggers/strategy mode
  (menutup temuan F-1 QA t_f2llm3).
- order_events.decision JSONB: audit keputusan agent LLM per G1 butir 3
  (reasoning, confidence, model, prompt_version, token usage, cycle id).
  Baris dengan decision IS NOT NULL adalah keputusan agent (termasuk HOLD,
  yang tidak punya order: order_id NULL + to_status 'AGENT_HOLD').

Revision: c003
Revises: b002
"""
from __future__ import annotations

from alembic import op

revision = "c003"
down_revision = "b002"
branch_labels = None
depends_on = None

SQL = r"""
-- Role model (temuan F-1 QA t_f2llm3): baris lama = admin (perilaku penuh
-- terjaga); user service agent dibuat dengan role 'agent' terpisah.
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'admin';
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_role_check
            CHECK (role IN ('admin', 'agent', 'user'));
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- Audit keputusan agent LLM (G1 butir 3): reasoning + confidence + model +
-- prompt version + token usage, append-only bersama order_events.
ALTER TABLE order_events ADD COLUMN IF NOT EXISTS decision JSONB;
-- Keputusan hold tanpa order: order_id NULL (AGENT_HOLD tanpa rantai order).
ALTER TABLE order_events ALTER COLUMN order_id DROP NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'order_events_decision_shape_check'
    ) THEN
        ALTER TABLE order_events ADD CONSTRAINT order_events_decision_shape_check
            CHECK (decision IS NULL OR (
                decision ? 'kind'
                AND decision ? 'reasoning'
                AND decision ? 'confidence'
                AND decision ? 'model'
                AND decision ? 'prompt_version'
            ));
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_order_events_decision
    ON order_events((decision->>'kind'), created_at);
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    # Kolom audit bersifat permanen (append-only ledger); downgrade dinonaktifkan.
    raise NotImplementedError("downgrade c003 dinonaktifkan (audit permanen)")
