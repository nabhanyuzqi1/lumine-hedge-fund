"""Skema v2.2 (PRD 19.3/19.4): 14 tabel baru + governance.

Tabel baru: strategies, strategy_versions, strategy_approvals, signals,
paper_runs, shadow_runs, regime_observations, risk_decisions, system_events,
reconciliation_runs, deployment_records, research_reports, settings_audit,
position_snapshots.

Governance:
- order_events append-only: UPDATE/DELETE/TRUNCATE ditolak trigger (PRD 19.4).
- strategy_approvals append-only (audit approval, PRD 11.2/18).
- strategy_versions immutable setelah final (PRD 11.1).
- settings -> settings_audit trigger (audit perubahan konfigurasi, PRD 18).
- liquidity_samples dikonversi ke partisi bulanan (retensi 90 hari).

Revision ID: b002
Revises: a001
Create Date: 2026-11-22
"""
from __future__ import annotations

from alembic import op

revision = "b002"
down_revision = "a001"
branch_labels = None
depends_on = None

SQL = r"""
-- ══════════════════════════════════════════════════════════════════════════
-- Strategy isolation & lifecycle (PRD §5, §10)
-- ══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS strategies (
    id              BIGSERIAL PRIMARY KEY,
    strategy_id     TEXT NOT NULL UNIQUE,       -- ID stabil lintas versi
    name            TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN
                     ('DRAFT', 'VALIDATING', 'BACKTEST_APPROVED', 'SHADOW', 'PAPER',
                      'LIVE_APPROVED', 'LIVE', 'DEGRADED', 'DISABLED', 'ARCHIVED')),
    environment     TEXT NOT NULL DEFAULT 'dev' CHECK (environment IN ('dev', 'staging', 'prod')),
    config          JSONB NOT NULL DEFAULT '{}',
    allowed_regimes JSONB NOT NULL DEFAULT '[]',   -- regime yang diizinkan (PRD 6.4)
    current_version TEXT,                          -- versi aktif (strategy_versions.version)
    enabled         BOOLEAN NOT NULL DEFAULT FALSE, -- enable eksplisit; restart tidak auto-live (PRD 5.2)
    circuit_breaker JSONB NOT NULL DEFAULT '{}',   -- {consecutive_errors, threshold, open_until}
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Immutable release (PRD 11.1): setiap versi menyimpan kode, hash, parameter,
-- laporan backtest/walk-forward/shadow/paper, risk profile, dan alasan.
CREATE TABLE IF NOT EXISTS strategy_versions (
    id                 BIGSERIAL PRIMARY KEY,
    strategy_id        TEXT NOT NULL REFERENCES strategies(strategy_id) ON DELETE RESTRICT,
    version            TEXT NOT NULL,
    code_commit_hash   TEXT,
    code_path          TEXT,
    params             JSONB NOT NULL DEFAULT '{}',
    config_hash        TEXT,
    data_version       TEXT,          -- versi/checksum dataset backtest (PRD 8.2)
    backtest_report    JSONB,
    walkforward_report JSONB,
    shadow_report      JSONB,
    paper_report       JSONB,
    risk_profile       JSONB,
    status             TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN
                        ('DRAFT', 'REVIEW', 'APPROVED', 'REJECTED', 'SUPERSEDED')),
    change_reason      TEXT,
    created_by         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at       TIMESTAMPTZ,
    deactivated_at     TIMESTAMPTZ,
    UNIQUE (strategy_id, version)
);
CREATE INDEX IF NOT EXISTS idx_strategy_versions_strategy
    ON strategy_versions(strategy_id, created_at);

-- Promotion workflow (PRD 11.2): setiap transisi punya bukti + aktor sah.
CREATE TABLE IF NOT EXISTS strategy_approvals (
    id                  BIGSERIAL PRIMARY KEY,
    strategy_version_id BIGINT NOT NULL REFERENCES strategy_versions(id) ON DELETE RESTRICT,
    stage               TEXT NOT NULL,   -- BACKTEST_REVIEW / SHADOW_REVIEW / PAPER_REVIEW /
                                         -- OWNER_APPROVAL / LIVE_APPROVAL / ROLLBACK
    decision            TEXT NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
    reviewer            TEXT NOT NULL,   -- username / telegram owner id / 'system'
    rationale           TEXT,
    evidence            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_strategy_approvals_version
    ON strategy_approvals(strategy_version_id, created_at);

-- Sinyal (PRD 5.2, 9.2): keluaran decide() yang divalidasi, lintas mode.
CREATE TABLE IF NOT EXISTS signals (
    id                BIGSERIAL PRIMARY KEY,
    strategy_id       TEXT NOT NULL,
    strategy_version  TEXT,
    symbol            TEXT NOT NULL,
    timeframe         TEXT NOT NULL,
    side              TEXT CHECK (side IN ('BUY', 'SELL')),  -- NULL = tidak entry
    order_intent      JSONB,      -- OrderIntent tervalidasi (PRD 4.1)
    regime_label      TEXT,
    regime_confidence NUMERIC(5, 4),
    regime_version    TEXT,
    features          JSONB NOT NULL DEFAULT '{}',
    reason            TEXT,
    source            TEXT NOT NULL CHECK (source IN ('LIVE', 'PAPER', 'SHADOW', 'BACKTEST')),
    status            TEXT NOT NULL DEFAULT 'EMITTED' CHECK (status IN
                       ('EMITTED', 'ACCEPTED', 'REJECTED', 'SUPERSEDED')),
    reject_reason     TEXT,
    ref_type          TEXT,        -- opsional: orders / paper_orders / backtest_runs
    ref_id            TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy_id, created_at);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol, created_at);

-- Registry paper run (PRD 8/9): satu baris per eksekusi paper/replay/walk-forward.
-- paper_orders.run_id menghubungkan trade ke run-nya.
CREATE TABLE IF NOT EXISTS paper_runs (
    id               BIGSERIAL PRIMARY KEY,
    run_id           UUID NOT NULL UNIQUE,
    strategy_id      TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    mode             TEXT NOT NULL DEFAULT 'PAPER' CHECK (mode IN ('PAPER', 'REPLAY', 'WALKFORWARD')),
    symbol           TEXT NOT NULL,
    timeframe        TEXT NOT NULL,
    period_start     TIMESTAMPTZ,
    period_end       TIMESTAMPTZ,
    starting_balance NUMERIC(14, 2),
    ending_balance   NUMERIC(14, 2),
    metrics          JSONB NOT NULL DEFAULT '{}',   -- metrik wajib PRD 8.3
    trade_count      INTEGER NOT NULL DEFAULT 0,
    config           JSONB NOT NULL DEFAULT '{}',
    data_provenance  JSONB NOT NULL DEFAULT '{}',   -- sumber, checksum, tanggal unduh (PRD 8.2)
    code_commit_hash TEXT,
    random_seed      BIGINT,
    status           TEXT NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_paper_runs_strategy ON paper_runs(strategy_id, created_at);
ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS run_id UUID REFERENCES paper_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_paper_orders_run ON paper_orders(run_id);

-- Registry shadow run (PRD 9): sinyal live tanpa order ke broker.
CREATE TABLE IF NOT EXISTS shadow_runs (
    id               BIGSERIAL PRIMARY KEY,
    run_id           UUID NOT NULL UNIQUE,
    strategy_id      TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    timeframe        TEXT NOT NULL,
    period_start     TIMESTAMPTZ,
    period_end       TIMESTAMPTZ,
    config           JSONB NOT NULL DEFAULT '{}',
    cost_model       JSONB NOT NULL DEFAULT '{}',   -- model fill konservatif (PRD 9.2)
    metrics          JSONB NOT NULL DEFAULT '{}',
    signal_count     INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    note             TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_shadow_runs_strategy ON shadow_runs(strategy_id, created_at);

-- Regime observation (PRD 6.4): label + confidence + data quality + alasan,
-- dicatat saat sinyal, saat order, dan selama posisi terbuka.
CREATE TABLE IF NOT EXISTS regime_observations (
    id                 BIGSERIAL PRIMARY KEY,
    symbol             TEXT NOT NULL,
    timeframe          TEXT NOT NULL,
    ts                 TIMESTAMPTZ NOT NULL,
    regime             TEXT NOT NULL CHECK (regime IN
                         ('TREND_UP', 'TREND_DOWN', 'RANGE', 'HIGH_VOLATILITY',
                          'LOW_LIQUIDITY', 'NEWS_OR_EVENT_RISK', 'UNKNOWN')),
    confidence         NUMERIC(5, 4),
    classifier_version TEXT NOT NULL,
    params             JSONB NOT NULL DEFAULT '{}',
    features           JSONB NOT NULL DEFAULT '{}',
    data_quality       JSONB NOT NULL DEFAULT '{}',  -- completeness, freshness, gap
    reason             TEXT,
    context            TEXT NOT NULL DEFAULT 'PERIODIC' CHECK (context IN
                         ('SIGNAL', 'ORDER', 'POSITION', 'PERIODIC')),
    ref_type           TEXT,
    ref_id             TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_regime_obs_symbol_ts ON regime_observations(symbol, ts);
CREATE INDEX IF NOT EXISTS idx_regime_obs_context ON regime_observations(context, ts);

-- Portfolio risk decision (PRD 7): setiap keputusan gate + inputnya.
CREATE TABLE IF NOT EXISTS risk_decisions (
    id              BIGSERIAL PRIMARY KEY,
    order_id        UUID REFERENCES orders(id),
    strategy_id     TEXT,
    decision        TEXT NOT NULL CHECK (decision IN ('PASS', 'REJECT')),
    reason_code     TEXT,
    reason          TEXT,
    inputs          JSONB NOT NULL DEFAULT '{}',    -- equity, balance, margin, open risk (PRD 7.2)
    limits_snapshot JSONB NOT NULL DEFAULT '{}',
    regime_label    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_decisions_order ON risk_decisions(order_id);
CREATE INDEX IF NOT EXISTS idx_risk_decisions_created ON risk_decisions(created_at);

-- System event bus (PRD 5.2: semua crash & keputusan supervisor dicatat; §18 audit).
CREATE TABLE IF NOT EXISTS system_events (
    id             BIGSERIAL PRIMARY KEY,
    event_type     TEXT NOT NULL,   -- SERVICE_START / SERVICE_CRASH / CIRCUIT_BREAKER /
                                    -- DEPLOY / CONFIG_CHANGE / DATA_QUALITY / ...
    severity       TEXT NOT NULL DEFAULT 'INFO' CHECK (severity IN ('INFO', 'WARN', 'ERROR', 'CRITICAL')),
    source         TEXT NOT NULL,   -- api / worker / ingest / reconciler / supervisor
    actor          TEXT,
    message        TEXT NOT NULL,
    details        JSONB NOT NULL DEFAULT '{}',
    correlation_id TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_system_events_type ON system_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_system_events_severity ON system_events(severity, created_at);

-- Reconciliation run (PRD 15): snapshot broker vs ledger + klasifikasi mismatch.
CREATE TABLE IF NOT EXISTS reconciliation_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL UNIQUE,
    trigger_source  TEXT NOT NULL CHECK (trigger_source IN
                     ('SCHEDULED', 'RECONNECT', 'API_RESTART', 'EA_RESTART', 'MANUAL', 'POST_ROLLBACK')),
    status          TEXT NOT NULL DEFAULT 'RUNNING' CHECK (status IN
                     ('RUNNING', 'COMPLETED', 'COMPLETED_WITH_MISMATCH', 'FAILED')),
    broker_snapshot JSONB NOT NULL DEFAULT '{}',
    ledger_summary  JSONB NOT NULL DEFAULT '{}',
    mismatches      JSONB NOT NULL DEFAULT '[]',
    mismatch_count  INTEGER NOT NULL DEFAULT 0,
    critical_count  INTEGER NOT NULL DEFAULT 0,
    action_taken    TEXT,   -- KILL_SWITCH / ALERT / NONE
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_reconciliation_runs_started ON reconciliation_runs(started_at);

-- Deployment record (PRD 17/18): audit deployment + migrasi.
CREATE TABLE IF NOT EXISTS deployment_records (
    id                BIGSERIAL PRIMARY KEY,
    service           TEXT NOT NULL,      -- api / paper-runner / alerts / ea-bridge
    version           TEXT,               -- commit hash / versi
    environment       TEXT NOT NULL CHECK (environment IN ('dev', 'staging', 'prod')),
    deploy_type       TEXT NOT NULL DEFAULT 'CODE' CHECK (deploy_type IN ('CODE', 'MIGRATION', 'CONFIG', 'EA')),
    migration_version TEXT,               -- alembic head saat deploy
    checksum          TEXT,
    deployed_by       TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'SUCCESS' CHECK (status IN ('SUCCESS', 'FAILED', 'ROLLED_BACK')),
    details           JSONB NOT NULL DEFAULT '{}',
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_deployment_records_service ON deployment_records(service, started_at);

-- Research report (PRD 12.3): laporan Hermes — fakta vs hipotesis dipisah.
CREATE TABLE IF NOT EXISTS research_reports (
    id                    BIGSERIAL PRIMARY KEY,
    title                 TEXT NOT NULL,
    report_type           TEXT NOT NULL DEFAULT 'WEEKLY' CHECK (report_type IN
                           ('WEEKLY', 'DIAGNOSIS', 'EXPERIMENT', 'REVIEW', 'OTHER')),
    period_start          TIMESTAMPTZ,
    period_end            TIMESTAMPTZ,
    data_sources          JSONB NOT NULL DEFAULT '{}',
    data_quality          JSONB NOT NULL DEFAULT '{}',
    summary               TEXT,
    findings              JSONB NOT NULL DEFAULT '[]',   -- temuan terukur (fakta)
    hypotheses            JSONB NOT NULL DEFAULT '[]',   -- hipotesis, bukan fakta (PRD 12.2)
    recommendations       JSONB NOT NULL DEFAULT '[]',
    baseline_vs_candidate JSONB NOT NULL DEFAULT '{}',
    risks                 JSONB NOT NULL DEFAULT '[]',
    author                TEXT NOT NULL DEFAULT 'hermes',
    status                TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN
                           ('DRAFT', 'QA_REVIEW', 'APPROVED', 'SUPERSEDED')),
    supersedes_id         BIGINT REFERENCES research_reports(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_research_reports_type ON research_reports(report_type, created_at);

-- Settings audit (PRD 18: audit trail perubahan konfigurasi).
CREATE TABLE IF NOT EXISTS settings_audit (
    id         BIGSERIAL PRIMARY KEY,
    key        TEXT NOT NULL,
    old_value  JSONB,
    new_value  JSONB,
    changed_by TEXT NOT NULL DEFAULT 'system',
    source     TEXT NOT NULL DEFAULT 'db',
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_settings_audit_key ON settings_audit(key, changed_at);

-- Position snapshot (PRD 19.1): deret waktu state posisi/portofolio.
CREATE TABLE IF NOT EXISTS position_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    position_id BIGINT REFERENCES positions(id),
    ticket      BIGINT,
    symbol      TEXT,
    side        TEXT CHECK (side IN ('BUY', 'SELL')),
    volume      NUMERIC(10, 2),
    price       NUMERIC(12, 5),
    profit      NUMERIC(14, 2),
    equity      NUMERIC(14, 2),
    balance     NUMERIC(14, 2),
    margin      NUMERIC(14, 2),
    free_margin NUMERIC(14, 2),
    open_risk   NUMERIC(14, 2),
    source      TEXT NOT NULL DEFAULT 'MONITOR' CHECK (source IN ('EA_SNAPSHOT', 'MONITOR', 'RECONCILER')),
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_ticket ON position_snapshots(ticket, ts);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_ts ON position_snapshots(ts);

-- ══════════════════════════════════════════════════════════════════════════
-- Governance triggers
-- ══════════════════════════════════════════════════════════════════════════

-- order_events append-only (PRD 19.4): koreksi hanya lewat event kompensasi.
CREATE OR REPLACE FUNCTION fund2_deny_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% pada % ditolak: tabel append-only (PRD 19.4); '
                    'gunakan event kompensasi, bukan mengedit sejarah',
                    TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS order_events_append_only ON order_events;
CREATE TRIGGER order_events_append_only
BEFORE UPDATE OR DELETE ON order_events
FOR EACH ROW EXECUTE FUNCTION fund2_deny_mutation();

DROP TRIGGER IF EXISTS order_events_no_truncate ON order_events;
CREATE TRIGGER order_events_no_truncate
BEFORE TRUNCATE ON order_events
FOR EACH STATEMENT EXECUTE FUNCTION fund2_deny_mutation();

-- strategy_approvals append-only (audit approval, PRD 11.2/18).
DROP TRIGGER IF EXISTS strategy_approvals_append_only ON strategy_approvals;
CREATE TRIGGER strategy_approvals_append_only
BEFORE UPDATE OR DELETE ON strategy_approvals
FOR EACH ROW EXECUTE FUNCTION fund2_deny_mutation();

-- strategy_versions immutable setelah final (PRD 11.1): versi yang pernah
-- disetujui/ditolak/ditindaklanjuti tidak boleh ditimpa; buat versi baru.
CREATE OR REPLACE FUNCTION fund2_guard_strategy_version() RETURNS trigger AS $$
BEGIN
    IF OLD.status IN ('APPROVED', 'REJECTED', 'SUPERSEDED') THEN
        RAISE EXCEPTION 'strategy_versions %/% sudah final (status %) dan immutable (PRD 11.1); '
                        'buat versi baru',
                        OLD.strategy_id, OLD.version, OLD.status;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS strategy_versions_immutable ON strategy_versions;
CREATE TRIGGER strategy_versions_immutable
BEFORE UPDATE OR DELETE ON strategy_versions
FOR EACH ROW EXECUTE FUNCTION fund2_guard_strategy_version();

-- settings -> settings_audit (PRD 18): setiap INSERT/UPDATE konfigurasi
-- tercatat. ea_last_seen_at dikecualikan (heartbeat, bukan keputusan konfig).
-- Aktor bisa di-set aplikasi via: SET app.actor = '<aktor>'.
CREATE OR REPLACE FUNCTION fund2_settings_audit() RETURNS trigger AS $$
BEGIN
    INSERT INTO settings_audit (key, old_value, new_value, changed_by, source)
    VALUES (
        NEW.key,
        CASE WHEN TG_OP = 'UPDATE' THEN OLD.value ELSE NULL END,
        NEW.value,
        COALESCE(NULLIF(current_setting('app.actor', true), ''), current_user),
        COALESCE(NULLIF(current_setting('app.source', true), ''), 'db')
    );
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS settings_audit_trail ON settings;
CREATE TRIGGER settings_audit_trail
AFTER INSERT OR UPDATE ON settings
FOR EACH ROW
WHEN (NEW.key <> 'ea_last_seen_at')
EXECUTE FUNCTION fund2_settings_audit();

-- ══════════════════════════════════════════════════════════════════════════
-- Partisi liquidity_samples (retensi 90 hari, volume ~14 ribu baris/hari)
-- Pola sama dengan candles: rename -> buat partisi -> salin -> drop legacy.
-- Seluruh migrasi berjalan dalam satu transaksi, jadi konversi atomik.
-- ══════════════════════════════════════════════════════════════════════════
DO $$
DECLARE
    m RECORD;
    min_ts TIMESTAMPTZ;
BEGIN
    IF to_regclass('public.liquidity_samples') IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM pg_partitioned_table pt
        JOIN pg_class c ON c.oid = pt.partrelid WHERE c.relname = 'liquidity_samples'
    ) THEN
        SELECT min(window_start) INTO min_ts FROM liquidity_samples;
        ALTER TABLE liquidity_samples RENAME TO liquidity_samples_legacy;
        CREATE TABLE liquidity_samples (
            symbol       TEXT NOT NULL,
            window_start TIMESTAMPTZ NOT NULL,
            session      TEXT NOT NULL,
            spread_avg   NUMERIC(12, 5) NOT NULL,
            spread_min   NUMERIC(12, 5) NOT NULL,
            spread_max   NUMERIC(12, 5) NOT NULL,
            tick_count   INTEGER NOT NULL,
            PRIMARY KEY (symbol, window_start)
        ) PARTITION BY RANGE (window_start);
        IF min_ts IS NOT NULL THEN
            FOR m IN
                SELECT generate_series(
                           date_trunc('month', min_ts)::date,
                           date_trunc('month', now() + interval '1 month')::date,
                           interval '1 month') AS m
            LOOP
                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS liquidity_samples_%s '
                    'PARTITION OF liquidity_samples FOR VALUES FROM (%L) TO (%L)',
                    to_char(m.m, 'YYYY_MM'), m.m, m.m + interval '1 month');
            END LOOP;
        END IF;
        INSERT INTO liquidity_samples SELECT * FROM liquidity_samples_legacy;
        DROP TABLE liquidity_samples_legacy;
    END IF;

    IF to_regclass('public.liquidity_samples') IS NOT NULL AND EXISTS (
        SELECT 1 FROM pg_partitioned_table pt
        JOIN pg_class c ON c.oid = pt.partrelid WHERE c.relname = 'liquidity_samples'
    ) THEN
        FOR m IN
            SELECT generate_series(
                       date_trunc('month', now())::date,
                       date_trunc('month', now() + interval '1 month')::date,
                       interval '1 month') AS m
        LOOP
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS liquidity_samples_%s '
                'PARTITION OF liquidity_samples FOR VALUES FROM (%L) TO (%L)',
                to_char(m.m, 'YYYY_MM'), m.m, m.m + interval '1 month');
        END LOOP;
        EXECUTE 'CREATE TABLE IF NOT EXISTS liquidity_samples_default PARTITION OF liquidity_samples DEFAULT';
    END IF;
END $$;

-- ══════════════════════════════════════════════════════════════════════════
-- Dokumentasi retensi in-DB (detail: docs/SCHEMA_v2.2.md)
-- ══════════════════════════════════════════════════════════════════════════
COMMENT ON TABLE order_events IS 'Append-only ledger (PRD 19.4). Retensi: PERMANEN. UPDATE/DELETE/TRUNCATE ditolak trigger; koreksi via event kompensasi.';
COMMENT ON TABLE candles IS 'Partisi bulanan. Retensi: 24 bulan (PRD 8.4 gerbang backtest >= 2 tahun); arsip ke Parquet sebelum partisi lama di-drop.';
COMMENT ON TABLE liquidity_samples IS 'Partisi bulanan. Retensi: 90 hari; data turunan yang dapat dihitung ulang dari tick Parquet (PRD 19.1).';
COMMENT ON TABLE position_snapshots IS 'Retensi: 180 hari.';
COMMENT ON TABLE signals IS 'Retensi: 12 bulan.';
COMMENT ON TABLE regime_observations IS 'Retensi: 12 bulan.';
COMMENT ON TABLE risk_decisions IS 'Retensi: 12 bulan.';
COMMENT ON TABLE system_events IS 'Retensi: 12 bulan.';
COMMENT ON TABLE sessions IS 'Retensi: kadaluarsa per expires_at; baris kedaluwarsa dibersihkan rutin.';
COMMENT ON TABLE settings_audit IS 'Retensi: PERMANEN (audit).';
COMMENT ON TABLE strategy_approvals IS 'Retensi: PERMANEN; append-only.';
COMMENT ON TABLE strategy_versions IS 'Retensi: PERMANEN; immutable setelah final.';
COMMENT ON TABLE backtest_runs IS 'Retensi: PERMANEN (audit anti-overfit, PRD 8.2: simpan semua parameter yang dicoba).';
COMMENT ON TABLE paper_runs IS 'Retensi: PERMANEN.';
COMMENT ON TABLE shadow_runs IS 'Retensi: PERMANEN.';
COMMENT ON TABLE reconciliation_runs IS 'Retensi: PERMANEN (audit).';
COMMENT ON TABLE deployment_records IS 'Retensi: PERMANEN (audit).';
COMMENT ON TABLE research_reports IS 'Retensi: PERMANEN.';
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    # Skema v2.2 tidak didrop otomatis: tabel audit/ledger bersifat permanen.
    raise NotImplementedError("downgrade v2.2 dinonaktifkan (audit/ledger permanen)")
