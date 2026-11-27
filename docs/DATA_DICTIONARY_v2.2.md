# Data Dictionary: Fund2 v2.2

| | |
| --- | --- |
| Digenerate | 2026-11-26 01:46 WIB |
| Sumber | DB live `fund2` @ 127.0.0.1:5433, **read-only** |
| Migrasi aktif (Alembic) | `l012` |
| Jumlah relasi (tabel + partisi) | 40 |
| Generator | `docs/gen_data_dictionary.py` |

Dokumen ini dihasilkan ulang dari katalog PostgreSQL, bukan diketik manual:
struktur yang tertulis di sini adalah struktur yang benar-benar ada di DB.
Peran tabel dan kebijakan retensi diambil dari `docs/SCHEMA_v2.2.md`
(keputusan retensi/partisi berbasis volume aktual).

Legenda: **PK** primary key, **FK** foreign key, **UQ** unique, **AO** append-only (trigger),
**IDX** indeks non-PK.

## 1. Ringkasan tabel

| Tabel | Peran | Baris | PK | Retensi |
| --- | --- | ---: | --- | --- |
| `alembic_version` | Versi migrasi aktif (Alembic) | 1 | version_num | permanen |
| `audit_log` | Audit aksi UI/API (aktor, aksi, target) | 610 | id | permanen |
| `backtest_runs` | Registry semua percobaan backtest/WF (PRD §8.2) | 1,432 | id | permanen |
| `bridge_commands` | Antrean command reconciler ke EA (P1b) | 0 | id | permanen |
| `candles` | OHLC M1+ (partisi bulanan) | 2,386,465 | symbol, timeframe, ts | 24 bulan lalu arsip Parquet |
| `data_quality_runs` | Hasil pemeriksaan kualitas data | 0 | id | permanen |
| `data_versions` | Provenance dataset (checksum, rentang) | 0 | symbol, timeframe | permanen |
| `degradation_events` | Riwayat transisi degradation state | 0 | id | permanen |
| `degradation_state` | State degradasi per strategi | 3 | strategy_id | permanen |
| `deployment_records` | Audit deployment/migrasi (PRD §17/§18) | 2 | id | permanen |
| `improvement_proposals` | Usulan self-improve + approval | 3 | id | permanen |
| `kill_switch_events` | Audit kill-switch (v2.1 §5.7, append-only) | 194 | id | permanen |
| `liquidity_samples_2026_11` | partisi | 63,100 | symbol, window_start | - |
| `liquidity_samples_2026_12` | partisi | 0 | symbol, window_start | - |
| `liquidity_samples_default` | partisi | 0 | symbol, window_start | - |
| `llm_introspections` | Introspeksi harian/per trade agent LLM | 30 | id | permanen |
| `login_failures` | Rate-limit login + forensik | 7 | username | 90 hari |
| `order_events` | Append-only ledger transisi status (PRD §19.4) | 9,168 | id | permanen |
| `orders` | Ledger order + state machine | 1,928 | id | permanen |
| `paper_orders` | Ledger paper trading | 27 | id | permanen |
| `paper_runs` | Registry run paper/replay/walk-forward | 0 | id | permanen |
| `paper_state` | State runner paper (key-value) | 8 | key | permanen |
| `position_snapshots` | Deret waktu state posisi/portofolio | 0 | id | 180 hari |
| `positions` | Posisi broker hasil snapshot | 249 | id | permanen |
| `reconciliation_runs` | Snapshot broker vs ledger (PRD §15) | 1 | id | permanen |
| `regime_observations` | Label regime + confidence (PRD §6.4) | 465 | id | 12 bulan |
| `research_proposals` | Usulan riset Hermes + keputusan | 1 | id | permanen |
| `research_reports` | Laporan riset Hermes (PRD §12.3) | 1 | id | permanen |
| `risk_decisions` | Keputusan risk gate + input (PRD §7) | 0 | id | 12 bulan |
| `sessions` | Sesi login (cookie + CSRF) | 342 | id | expires_at + 30 hari |
| `settings` | Konfigurasi runtime JSONB (nilai aktif) | 38 | key | permanen |
| `settings_audit` | Audit perubahan konfigurasi | 327 | id | permanen |
| `shadow_runs` | Registry run shadow (PRD §9) | 52 | id | permanen |
| `shadow_signals` | Sinyal shadow + simulasi hasil | 2 | id | permanen |
| `signals` | Keluaran decide() lintas mode | 21 | id | 12 bulan |
| `strategies` | Lifecycle strategi (PRD §5.3) | 4 | id | permanen |
| `strategy_approvals` | Audit approval strategi (append-only) | 8 | id | permanen |
| `strategy_versions` | Rilis strategi immutable (PRD §11.1) | 3 | id | permanen |
| `system_events` | Event bus supervisor/audit (PRD §5.2, §18) | 13 | id | 12 bulan |
| `users` | Akun dashboard | 12 | id | permanen |

## 2. Partisi & retensi

| Tabel induk | Partisi | Bound |
| --- | --- | --- |
| `liquidity_samples` | `liquidity_samples_2026_11` | `FOR VALUES FROM ('2026-11-01 00:00:00+07') TO ('2026-12-01 00:00:00+07')` |
| `liquidity_samples` | `liquidity_samples_2026_12` | `FOR VALUES FROM ('2026-12-01 00:00:00+07') TO ('2027-01-01 00:00:00+07')` |
| `liquidity_samples` | `liquidity_samples_default` | `DEFAULT` |
| `liquidity_samples_pkey1` | `liquidity_samples_2026_11_pkey` | `None` |
| `liquidity_samples_pkey1` | `liquidity_samples_2026_12_pkey` | `None` |
| `liquidity_samples_pkey1` | `liquidity_samples_default_pkey` | `None` |

Kebijakan retensi (dari `SCHEMA_v2.2.md`): partisi bulanan diganti arsip Parquet
sebelum drop; `order_events`, `strategy_approvals`, `kill_switch_events` tidak pernah
dihapus (append-only, kebutuhan audit).

## 3. Kamus kolom per tabel

### `alembic_version`: Versi migrasi aktif (Alembic)

- Baris: **1** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `version_num` | character varying(32) | tidak | - | PK |

Indeks:
- `alembic_version_pkc`: `CREATE UNIQUE INDEX alembic_version_pkc ON public.alembic_version USING btree (version_num)`

### `audit_log`: Audit aksi UI/API (aktor, aksi, target)

- Baris: **610** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('audit_log_id_seq'::regclass)` | PK |
| 2 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 3 | `actor` | text | tidak | - | - |
| 4 | `actor_role` | text | ya | - | - |
| 5 | `action` | text | tidak | - | - |
| 6 | `object` | text | ya | - | - |
| 7 | `details` | jsonb | tidak | `'{}'::jsonb` | - |
| 8 | `ip` | text | ya | - | - |

Indeks:
- `idx_audit_log_action`: `CREATE INDEX idx_audit_log_action ON public.audit_log USING btree (action, created_at)`
- `idx_audit_log_actor`: `CREATE INDEX idx_audit_log_actor ON public.audit_log USING btree (actor, created_at)`
- `idx_audit_log_created`: `CREATE INDEX idx_audit_log_created ON public.audit_log USING btree (created_at)`

### `backtest_runs`: Registry semua percobaan backtest/WF (PRD §8.2)

- Baris: **1,432** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('backtest_runs_id_seq'::regclass)` | PK |
| 2 | `run_id` | uuid | tidak | - | - |
| 3 | `strategy_id` | text | tidak | - | - |
| 4 | `strategy_version` | text | tidak | - | - |
| 5 | `symbol` | text | tidak | - | - |
| 6 | `timeframe` | text | tidak | - | - |
| 7 | `role` | text | tidak | - | - |
| 8 | `window_index` | integer | tidak | `0` | - |
| 9 | `train_start` | timestamp with time zone | ya | - | - |
| 10 | `train_end` | timestamp with time zone | ya | - | - |
| 11 | `test_start` | timestamp with time zone | ya | - | - |
| 12 | `test_end` | timestamp with time zone | ya | - | - |
| 13 | `params` | jsonb | tidak | `'{}'::jsonb` | - |
| 14 | `config` | jsonb | tidak | `'{}'::jsonb` | - |
| 15 | `metrics` | jsonb | tidak | `'{}'::jsonb` | - |
| 16 | `selected` | boolean | tidak | `false` | - |
| 17 | `note` | text | ya | - | - |
| 18 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_backtest_runs_run`: `CREATE INDEX idx_backtest_runs_run ON public.backtest_runs USING btree (run_id)`
- `idx_backtest_runs_strategy`: `CREATE INDEX idx_backtest_runs_strategy ON public.backtest_runs USING btree (strategy_id, created_at)`

Constraint CHECK:
- `backtest_runs_role_check`: `CHECK ((role = ANY (ARRAY['train'::text, 'test'::text])))`

### `bridge_commands`: Antrean command reconciler ke EA (P1b)

- Baris: **0** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | uuid | tidak | `gen_random_uuid()` | PK |
| 2 | `order_id` | uuid | ya | - | FK→`orders`.`id` (NO ACTION) |
| 3 | `action` | text | tidak | - | - |
| 4 | `payload` | jsonb | tidak | `'{}'::jsonb` | - |
| 5 | `status` | text | tidak | `'QUEUED'::text` | - |
| 6 | `fail_reason` | text | ya | - | - |
| 7 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 8 | `delivered_at` | timestamp with time zone | ya | - | - |
| 9 | `resolved_at` | timestamp with time zone | ya | - | - |

Indeks:
- `idx_bridge_commands_status`: `CREATE INDEX idx_bridge_commands_status ON public.bridge_commands USING btree (status, created_at)`

### `candles`: OHLC M1+ (partisi bulanan)

- Baris: **2,386,465** · Retensi: 24 bulan lalu arsip Parquet

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `symbol` | text | tidak | - | PK |
| 2 | `timeframe` | text | tidak | - | PK |
| 3 | `ts` | timestamp with time zone | tidak | - | PK |
| 4 | `open` | numeric | tidak | - | - |
| 5 | `high` | numeric | tidak | - | - |
| 6 | `low` | numeric | tidak | - | - |
| 7 | `close` | numeric | tidak | - | - |
| 8 | `volume` | numeric | tidak | `0` | - |

### `data_quality_runs`: Hasil pemeriksaan kualitas data

- Baris: **0** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('data_quality_runs_id_seq'::regclass)` | PK |
| 2 | `run_at` | timestamp with time zone | tidak | `now()` | - |
| 3 | `status` | text | tidak | - | - |
| 4 | `report` | jsonb | tidak | - | - |
| 5 | `checks_failed` | integer | tidak | `0` | - |
| 6 | `checks_warned` | integer | tidak | `0` | - |

Indeks:
- `idx_data_quality_runs_run`: `CREATE INDEX idx_data_quality_runs_run ON public.data_quality_runs USING btree (run_at DESC)`

Constraint CHECK:
- `data_quality_runs_status_check`: `CHECK ((status = ANY (ARRAY['PASS'::text, 'WARN'::text, 'FAIL'::text])))`

### `data_versions`: Provenance dataset (checksum, rentang)

- Baris: **0** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `symbol` | text | tidak | - | PK |
| 2 | `timeframe` | text | tidak | - | PK |
| 3 | `row_count` | integer | tidak | `0` | - |
| 4 | `checksum` | text | tidak | - | - |
| 5 | `updated_at` | timestamp with time zone | tidak | `now()` | - |

### `degradation_events`: Riwayat transisi degradation state

- Baris: **0** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('degradation_events_id_seq'::regclass)` | PK |
| 2 | `strategy_id` | text | tidak | - | - |
| 3 | `from_status` | text | ya | - | - |
| 4 | `to_status` | text | tidak | - | - |
| 5 | `trigger` | text | tidak | - | - |
| 6 | `reason` | text | ya | - | - |
| 7 | `indicators` | jsonb | tidak | `'[]'::jsonb` | - |
| 8 | `config_version` | text | tidak | `'1.0.0'::text` | - |
| 9 | `config_hash` | text | tidak | `''::text` | - |
| 10 | `actor` | text | ya | - | - |
| 11 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_degradation_events_strategy`: `CREATE INDEX idx_degradation_events_strategy ON public.degradation_events USING btree (strategy_id, created_at)`

Constraint CHECK:
- `degradation_events_trigger_check`: `CHECK ((trigger = ANY (ARRAY['EVALUATION'::text, 'REENABLE_OWNER'::text])))`

Trigger:
- `degradation_events_append_only`: `CREATE TRIGGER degradation_events_append_only BEFORE DELETE OR UPDATE ON public.degradation_events FOR EACH ROW EXECUTE FUNCTION fund2_deny_mutation()`

### `degradation_state`: State degradasi per strategi

- Baris: **3** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `strategy_id` | text | tidak | - | PK |
| 2 | `status` | text | tidak | `'NORMAL'::text` | - |
| 3 | `since` | timestamp with time zone | ya | - | - |
| 4 | `last_evaluated_at` | timestamp with time zone | ya | - | - |
| 5 | `cooldown_until` | timestamp with time zone | ya | - | - |
| 6 | `confirm_status` | text | ya | - | - |
| 7 | `confirm_count` | integer | tidak | `0` | - |
| 8 | `confirm_trades_start` | integer | tidak | `0` | - |
| 9 | `indicators` | jsonb | tidak | `'[]'::jsonb` | - |
| 10 | `config_version` | text | tidak | `'1.0.0'::text` | - |
| 11 | `config_hash` | text | tidak | `''::text` | - |
| 12 | `state` | jsonb | tidak | `'{}'::jsonb` | - |
| 13 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 14 | `updated_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_degradation_state_status`: `CREATE INDEX idx_degradation_state_status ON public.degradation_state USING btree (status)`

Constraint CHECK:
- `degradation_state_status_check`: `CHECK ((status = ANY (ARRAY['NORMAL'::text, 'WATCH'::text, 'DEGRADED'::text, 'HALTED'::text])))`

### `deployment_records`: Audit deployment/migrasi (PRD §17/§18)

- Baris: **2** · Retensi: permanen · append-only

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('deployment_records_id_seq'::regclass)` | PK |
| 2 | `service` | text | tidak | - | - |
| 3 | `version` | text | ya | - | - |
| 4 | `environment` | text | tidak | - | - |
| 5 | `deploy_type` | text | tidak | `'CODE'::text` | - |
| 6 | `migration_version` | text | ya | - | - |
| 7 | `checksum` | text | ya | - | - |
| 8 | `deployed_by` | text | tidak | - | - |
| 9 | `status` | text | tidak | `'SUCCESS'::text` | - |
| 10 | `details` | jsonb | tidak | `'{}'::jsonb` | - |
| 11 | `started_at` | timestamp with time zone | tidak | `now()` | - |
| 12 | `finished_at` | timestamp with time zone | ya | - | - |

Indeks:
- `idx_deployment_records_service`: `CREATE INDEX idx_deployment_records_service ON public.deployment_records USING btree (service, started_at)`

Constraint CHECK:
- `deployment_records_deploy_type_check`: `CHECK ((deploy_type = ANY (ARRAY['CODE'::text, 'MIGRATION'::text, 'CONFIG'::text, 'EA'::text])))`
- `deployment_records_environment_check`: `CHECK ((environment = ANY (ARRAY['dev'::text, 'staging'::text, 'prod'::text])))`
- `deployment_records_status_check`: `CHECK ((status = ANY (ARRAY['SUCCESS'::text, 'FAILED'::text, 'ROLLED_BACK'::text])))`

### `improvement_proposals`: Usulan self-improve + approval

- Baris: **3** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | text | tidak | - | PK |
| 2 | `week` | text | tidak | - | - |
| 3 | `title` | text | tidak | - | - |
| 4 | `hypothesis` | text | tidak | - | - |
| 5 | `change` | jsonb | tidak | `'{}'::jsonb` | - |
| 6 | `analysis` | jsonb | tidak | `'{}'::jsonb` | - |
| 7 | `backtest_run_ids` | jsonb | tidak | `'[]'::jsonb` | - |
| 8 | `evidence` | jsonb | tidak | `'{}'::jsonb` | - |
| 9 | `verdict` | text | tidak | `'PENDING'::text` | - |
| 10 | `criteria_result` | jsonb | tidak | `'{}'::jsonb` | - |
| 11 | `status` | text | tidak | `'PROPOSED'::text` | - |
| 12 | `strategy_version_id` | bigint | ya | - | FK→`strategy_versions`.`id` (NO ACTION) |
| 13 | `reviewer` | text | ya | - | - |
| 14 | `rationale` | text | ya | - | - |
| 15 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 16 | `decided_at` | timestamp with time zone | ya | - | - |
| 17 | `deployed_at` | timestamp with time zone | ya | - | - |

Indeks:
- `idx_improvement_proposals_week`: `CREATE INDEX idx_improvement_proposals_week ON public.improvement_proposals USING btree (week DESC)`

Constraint CHECK:
- `improvement_proposals_status_check`: `CHECK ((status = ANY (ARRAY['PROPOSED'::text, 'APPROVED'::text, 'REJECTED'::text, 'DEPLOYED'::text])))`
- `improvement_proposals_verdict_check`: `CHECK ((verdict = ANY (ARRAY['PENDING'::text, 'LULUS'::text, 'GAGAL'::text])))`

### `kill_switch_events`: Audit kill-switch (v2.1 §5.7, append-only)

- Baris: **194** · Retensi: permanen · append-only

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('kill_switch_events_id_seq'::regclass)` | PK |
| 2 | `action` | text | tidak | - | - |
| 3 | `mode` | text | ya | - | - |
| 4 | `strategy` | text | ya | - | - |
| 5 | `source` | text | tidak | - | - |
| 6 | `actor` | text | tidak | - | - |
| 7 | `reason` | text | ya | - | - |
| 8 | `details` | jsonb | tidak | `'{}'::jsonb` | - |
| 9 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_kill_switch_events_created`: `CREATE INDEX idx_kill_switch_events_created ON public.kill_switch_events USING btree (created_at)`

### `liquidity_samples_2026_11`: (lihat migrasi / kode)

- Baris: **63,100** · Retensi: -

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `symbol` | text | tidak | - | PK |
| 2 | `window_start` | timestamp with time zone | tidak | - | PK |
| 3 | `session` | text | tidak | - | - |
| 4 | `spread_avg` | numeric | tidak | - | - |
| 5 | `spread_min` | numeric | tidak | - | - |
| 6 | `spread_max` | numeric | tidak | - | - |
| 7 | `tick_count` | integer | tidak | - | - |

### `liquidity_samples_2026_12`: (lihat migrasi / kode)

- Baris: **0** · Retensi: -

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `symbol` | text | tidak | - | PK |
| 2 | `window_start` | timestamp with time zone | tidak | - | PK |
| 3 | `session` | text | tidak | - | - |
| 4 | `spread_avg` | numeric | tidak | - | - |
| 5 | `spread_min` | numeric | tidak | - | - |
| 6 | `spread_max` | numeric | tidak | - | - |
| 7 | `tick_count` | integer | tidak | - | - |

### `liquidity_samples_default`: (lihat migrasi / kode)

- Baris: **0** · Retensi: -

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `symbol` | text | tidak | - | PK |
| 2 | `window_start` | timestamp with time zone | tidak | - | PK |
| 3 | `session` | text | tidak | - | - |
| 4 | `spread_avg` | numeric | tidak | - | - |
| 5 | `spread_min` | numeric | tidak | - | - |
| 6 | `spread_max` | numeric | tidak | - | - |
| 7 | `tick_count` | integer | tidak | - | - |

### `llm_introspections`: Introspeksi harian/per trade agent LLM

- Baris: **30** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('llm_introspections_id_seq'::regclass)` | PK |
| 2 | `scope` | text | tidak | - | UQ |
| 3 | `ref_key` | text | tidak | - | UQ |
| 4 | `evidence` | jsonb | ya | - | - |
| 5 | `narasi` | text | ya | - | - |
| 6 | `model` | text | ya | - | - |
| 7 | `prompt_version` | text | ya | - | - |
| 8 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_llm_introspections_scope`: `CREATE INDEX idx_llm_introspections_scope ON public.llm_introspections USING btree (scope, created_at)`
- `llm_introspections_scope_ref_key_key`: `CREATE UNIQUE INDEX llm_introspections_scope_ref_key_key ON public.llm_introspections USING btree (scope, ref_key)`

Constraint CHECK:
- `llm_introspections_scope_check`: `CHECK ((scope = ANY (ARRAY['trade'::text, 'daily'::text])))`

Trigger:
- `llm_introspections_append_only`: `CREATE TRIGGER llm_introspections_append_only BEFORE DELETE OR UPDATE ON public.llm_introspections FOR EACH ROW EXECUTE FUNCTION fund2_deny_mutation()`

### `login_failures`: Rate-limit login + forensik

- Baris: **7** · Retensi: 90 hari

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `username` | text | tidak | - | PK |
| 2 | `failed_count` | integer | tidak | `0` | - |
| 3 | `lock_events` | integer | tidak | `0` | - |
| 4 | `locked_until` | timestamp with time zone | ya | - | - |
| 5 | `updated_at` | timestamp with time zone | tidak | `now()` | - |

### `order_events`: Append-only ledger transisi status (PRD §19.4)

- Baris: **9,168** · Retensi: permanen · append-only

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('order_events_id_seq'::regclass)` | PK |
| 2 | `order_id` | uuid | ya | - | FK→`orders`.`id` (CASCADE) |
| 3 | `from_status` | text | ya | - | - |
| 4 | `to_status` | text | tidak | - | - |
| 5 | `payload` | jsonb | tidak | `'{}'::jsonb` | - |
| 6 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 7 | `decision` | jsonb | ya | - | - |

Indeks:
- `idx_order_events_decision`: `CREATE INDEX idx_order_events_decision ON public.order_events USING btree (((decision ->> 'kind'::text)), created_at)`
- `idx_order_events_order`: `CREATE INDEX idx_order_events_order ON public.order_events USING btree (order_id, id)`

Constraint CHECK:
- `order_events_decision_shape_check`: `CHECK (((decision IS NULL) OR ((decision ? 'kind'::text) AND (decision ? 'reasoning'::text) AND (decision ? 'confidence'::text) AND (decision ? 'model'::text) AND (decision ? 'prompt_version'::text))))`

Trigger:
- `order_events_append_only`: `CREATE TRIGGER order_events_append_only BEFORE DELETE OR UPDATE ON public.order_events FOR EACH ROW EXECUTE FUNCTION fund2_deny_mutation()`
- `order_events_no_truncate`: `CREATE TRIGGER order_events_no_truncate BEFORE TRUNCATE ON public.order_events FOR EACH STATEMENT EXECUTE FUNCTION fund2_deny_mutation()`

### `orders`: Ledger order + state machine

- Baris: **1,928** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | uuid | tidak | `gen_random_uuid()` | PK |
| 2 | `command_id` | uuid | tidak | `gen_random_uuid()` | UQ |
| 3 | `user_id` | bigint | ya | - | FK→`users`.`id` (NO ACTION) |
| 4 | `symbol` | text | tidak | - | - |
| 5 | `side` | text | tidak | - | - |
| 6 | `volume` | numeric | tidak | - | - |
| 7 | `sl` | numeric | ya | - | - |
| 8 | `tp` | numeric | ya | - | - |
| 9 | `status` | text | tidak | `'RECEIVED'::text` | - |
| 10 | `price_requested` | numeric | ya | - | - |
| 11 | `ticket` | bigint | ya | - | - |
| 12 | `price_filled` | numeric | ya | - | - |
| 13 | `fail_reason` | text | ya | - | - |
| 14 | `strategy` | text | tidak | `'manual'::text` | - |
| 15 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 16 | `updated_at` | timestamp with time zone | tidak | `now()` | - |
| 17 | `sent_at` | timestamp with time zone | ya | - | - |
| 18 | `delivered_at` | timestamp with time zone | ya | - | - |
| 19 | `resolved_at` | timestamp with time zone | ya | - | - |
| 20 | `action` | text | tidak | `'OPEN'::text` | - |

Indeks:
- `idx_orders_sent`: `CREATE INDEX idx_orders_sent ON public.orders USING btree (sent_at) WHERE (status = 'SENT'::text)`
- `idx_orders_status`: `CREATE INDEX idx_orders_status ON public.orders USING btree (status, created_at)`
- `orders_command_id_key`: `CREATE UNIQUE INDEX orders_command_id_key ON public.orders USING btree (command_id)`

Constraint CHECK:
- `orders_side_check`: `CHECK ((side = ANY (ARRAY['BUY'::text, 'SELL'::text])))`

### `paper_orders`: Ledger paper trading

- Baris: **27** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | uuid | tidak | `gen_random_uuid()` | PK |
| 2 | `mode` | text | tidak | `'PAPER'::text` | - |
| 3 | `strategy` | text | tidak | - | - |
| 4 | `symbol` | text | tidak | - | - |
| 5 | `side` | text | tidak | - | - |
| 6 | `volume` | numeric | tidak | - | - |
| 7 | `sl` | numeric | tidak | - | - |
| 8 | `tp` | numeric | tidak | - | - |
| 9 | `status` | text | tidak | `'OPEN'::text` | - |
| 10 | `risk_decision` | jsonb | tidak | `'{}'::jsonb` | - |
| 11 | `entry_price` | numeric | ya | - | - |
| 12 | `exit_price` | numeric | ya | - | - |
| 13 | `profit` | numeric | tidak | `0` | - |
| 14 | `reason` | text | ya | - | - |
| 15 | `opened_at` | timestamp with time zone | ya | - | - |
| 16 | `closed_at` | timestamp with time zone | ya | - | - |
| 17 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 18 | `run_id` | uuid | ya | - | FK→`paper_runs`.`run_id` (NO ACTION) |

Indeks:
- `idx_paper_orders_mode`: `CREATE INDEX idx_paper_orders_mode ON public.paper_orders USING btree (mode, strategy, created_at)`
- `idx_paper_orders_run`: `CREATE INDEX idx_paper_orders_run ON public.paper_orders USING btree (run_id)`
- `idx_paper_orders_status`: `CREATE INDEX idx_paper_orders_status ON public.paper_orders USING btree (status, created_at)`

Constraint CHECK:
- `paper_orders_mode_check`: `CHECK ((mode = ANY (ARRAY['PAPER'::text, 'REPLAY'::text])))`
- `paper_orders_side_check`: `CHECK ((side = ANY (ARRAY['BUY'::text, 'SELL'::text])))`
- `paper_orders_status_check`: `CHECK ((status = ANY (ARRAY['OPEN'::text, 'CLOSED'::text, 'REJECTED'::text])))`

### `paper_runs`: Registry run paper/replay/walk-forward

- Baris: **0** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('paper_runs_id_seq'::regclass)` | PK |
| 2 | `run_id` | uuid | tidak | - | UQ |
| 3 | `strategy_id` | text | tidak | - | - |
| 4 | `strategy_version` | text | tidak | - | - |
| 5 | `mode` | text | tidak | `'PAPER'::text` | - |
| 6 | `symbol` | text | tidak | - | - |
| 7 | `timeframe` | text | tidak | - | - |
| 8 | `period_start` | timestamp with time zone | ya | - | - |
| 9 | `period_end` | timestamp with time zone | ya | - | - |
| 10 | `starting_balance` | numeric | ya | - | - |
| 11 | `ending_balance` | numeric | ya | - | - |
| 12 | `metrics` | jsonb | tidak | `'{}'::jsonb` | - |
| 13 | `trade_count` | integer | tidak | `0` | - |
| 14 | `config` | jsonb | tidak | `'{}'::jsonb` | - |
| 15 | `data_provenance` | jsonb | tidak | `'{}'::jsonb` | - |
| 16 | `code_commit_hash` | text | ya | - | - |
| 17 | `random_seed` | bigint | ya | - | - |
| 18 | `status` | text | tidak | `'RUNNING'::text` | - |
| 19 | `error` | text | ya | - | - |
| 20 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 21 | `completed_at` | timestamp with time zone | ya | - | - |

Indeks:
- `idx_paper_runs_strategy`: `CREATE INDEX idx_paper_runs_strategy ON public.paper_runs USING btree (strategy_id, created_at)`
- `paper_runs_run_id_key`: `CREATE UNIQUE INDEX paper_runs_run_id_key ON public.paper_runs USING btree (run_id)`

Constraint CHECK:
- `paper_runs_mode_check`: `CHECK ((mode = ANY (ARRAY['PAPER'::text, 'REPLAY'::text, 'WALKFORWARD'::text])))`
- `paper_runs_status_check`: `CHECK ((status = ANY (ARRAY['RUNNING'::text, 'COMPLETED'::text, 'FAILED'::text])))`

### `paper_state`: State runner paper (key-value)

- Baris: **8** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `key` | text | tidak | - | PK |
| 2 | `value` | jsonb | tidak | - | - |
| 3 | `updated_at` | timestamp with time zone | tidak | `now()` | - |

### `position_snapshots`: Deret waktu state posisi/portofolio

- Baris: **0** · Retensi: 180 hari

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('position_snapshots_id_seq'::regclass)` | PK |
| 2 | `position_id` | bigint | ya | - | FK→`positions`.`id` (NO ACTION) |
| 3 | `ticket` | bigint | ya | - | - |
| 4 | `symbol` | text | ya | - | - |
| 5 | `side` | text | ya | - | - |
| 6 | `volume` | numeric | ya | - | - |
| 7 | `price` | numeric | ya | - | - |
| 8 | `profit` | numeric | ya | - | - |
| 9 | `equity` | numeric | ya | - | - |
| 10 | `balance` | numeric | ya | - | - |
| 11 | `margin` | numeric | ya | - | - |
| 12 | `free_margin` | numeric | ya | - | - |
| 13 | `open_risk` | numeric | ya | - | - |
| 14 | `source` | text | tidak | `'MONITOR'::text` | - |
| 15 | `ts` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_position_snapshots_ticket`: `CREATE INDEX idx_position_snapshots_ticket ON public.position_snapshots USING btree (ticket, ts)`
- `idx_position_snapshots_ts`: `CREATE INDEX idx_position_snapshots_ts ON public.position_snapshots USING btree (ts)`

Constraint CHECK:
- `position_snapshots_side_check`: `CHECK ((side = ANY (ARRAY['BUY'::text, 'SELL'::text])))`
- `position_snapshots_source_check`: `CHECK ((source = ANY (ARRAY['EA_SNAPSHOT'::text, 'MONITOR'::text, 'RECONCILER'::text])))`

### `positions`: Posisi broker hasil snapshot

- Baris: **249** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('positions_id_seq'::regclass)` | PK |
| 2 | `ticket` | bigint | tidak | - | UQ |
| 3 | `order_id` | uuid | ya | - | FK→`orders`.`id` (NO ACTION) |
| 4 | `symbol` | text | tidak | - | - |
| 5 | `side` | text | tidak | - | - |
| 6 | `volume` | numeric | tidak | - | - |
| 7 | `open_price` | numeric | ya | - | - |
| 8 | `open_time` | timestamp with time zone | ya | - | - |
| 9 | `close_price` | numeric | ya | - | - |
| 10 | `close_time` | timestamp with time zone | ya | - | - |
| 11 | `profit` | numeric | tidak | `0` | - |
| 12 | `status` | text | tidak | `'OPEN'::text` | - |
| 13 | `raw` | jsonb | tidak | `'{}'::jsonb` | - |
| 14 | `updated_at` | timestamp with time zone | tidak | `now()` | - |
| 15 | `sl` | numeric | ya | - | - |
| 16 | `tp` | numeric | ya | - | - |

Indeks:
- `idx_positions_status`: `CREATE INDEX idx_positions_status ON public.positions USING btree (status)`
- `positions_ticket_key`: `CREATE UNIQUE INDEX positions_ticket_key ON public.positions USING btree (ticket)`

Constraint CHECK:
- `positions_side_check`: `CHECK ((side = ANY (ARRAY['BUY'::text, 'SELL'::text])))`
- `positions_status_check`: `CHECK ((status = ANY (ARRAY['OPEN'::text, 'CLOSED'::text])))`

### `reconciliation_runs`: Snapshot broker vs ledger (PRD §15)

- Baris: **1** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('reconciliation_runs_id_seq'::regclass)` | PK |
| 2 | `run_id` | uuid | tidak | - | UQ |
| 3 | `trigger_source` | text | tidak | - | - |
| 4 | `status` | text | tidak | `'RUNNING'::text` | - |
| 5 | `broker_snapshot` | jsonb | tidak | `'{}'::jsonb` | - |
| 6 | `ledger_summary` | jsonb | tidak | `'{}'::jsonb` | - |
| 7 | `mismatches` | jsonb | tidak | `'[]'::jsonb` | - |
| 8 | `mismatch_count` | integer | tidak | `0` | - |
| 9 | `critical_count` | integer | tidak | `0` | - |
| 10 | `action_taken` | text | ya | - | - |
| 11 | `started_at` | timestamp with time zone | tidak | `now()` | - |
| 12 | `finished_at` | timestamp with time zone | ya | - | - |

Indeks:
- `idx_reconciliation_runs_started`: `CREATE INDEX idx_reconciliation_runs_started ON public.reconciliation_runs USING btree (started_at)`
- `reconciliation_runs_run_id_key`: `CREATE UNIQUE INDEX reconciliation_runs_run_id_key ON public.reconciliation_runs USING btree (run_id)`

Constraint CHECK:
- `reconciliation_runs_status_check`: `CHECK ((status = ANY (ARRAY['RUNNING'::text, 'COMPLETED'::text, 'COMPLETED_WITH_MISMATCH'::text, 'FAILED'::text])))`
- `reconciliation_runs_trigger_source_check`: `CHECK ((trigger_source = ANY (ARRAY['SCHEDULED'::text, 'RECONNECT'::text, 'API_RESTART'::text, 'EA_RESTART'::text, 'MANUAL'::text, 'POST_ROLLBACK'::text])))`

### `regime_observations`: Label regime + confidence (PRD §6.4)

- Baris: **465** · Retensi: 12 bulan

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('regime_observations_id_seq'::regclass)` | PK |
| 2 | `symbol` | text | tidak | - | - |
| 3 | `timeframe` | text | tidak | - | - |
| 4 | `ts` | timestamp with time zone | tidak | - | - |
| 5 | `regime` | text | tidak | - | - |
| 6 | `confidence` | numeric | ya | - | - |
| 7 | `classifier_version` | text | tidak | - | - |
| 8 | `params` | jsonb | tidak | `'{}'::jsonb` | - |
| 9 | `features` | jsonb | tidak | `'{}'::jsonb` | - |
| 10 | `data_quality` | jsonb | tidak | `'{}'::jsonb` | - |
| 11 | `reason` | text | ya | - | - |
| 12 | `context` | text | tidak | `'PERIODIC'::text` | - |
| 13 | `ref_type` | text | ya | - | - |
| 14 | `ref_id` | text | ya | - | - |
| 15 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_regime_obs_context`: `CREATE INDEX idx_regime_obs_context ON public.regime_observations USING btree (context, ts)`
- `idx_regime_obs_symbol_ts`: `CREATE INDEX idx_regime_obs_symbol_ts ON public.regime_observations USING btree (symbol, ts)`

Constraint CHECK:
- `regime_observations_context_check`: `CHECK ((context = ANY (ARRAY['SIGNAL'::text, 'ORDER'::text, 'POSITION'::text, 'PERIODIC'::text])))`
- `regime_observations_regime_check`: `CHECK ((regime = ANY (ARRAY['TREND_UP'::text, 'TREND_DOWN'::text, 'RANGE'::text, 'HIGH_VOLATILITY'::text, 'LOW_LIQUIDITY'::text, 'NEWS_OR_EVENT_RISK'::text, 'UNKNOWN'::text])))`

### `research_proposals`: Usulan riset Hermes + keputusan

- Baris: **1** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('research_proposals_id_seq'::regclass)` | PK |
| 2 | `proposal_type` | text | tidak | `'EXPERIMENT'::text` | - |
| 3 | `title` | text | tidak | - | - |
| 4 | `hypothesis` | text | tidak | `''::text` | - |
| 5 | `report_id` | bigint | ya | - | FK→`research_reports`.`id` (NO ACTION) |
| 6 | `change` | jsonb | tidak | `'{}'::jsonb` | - |
| 7 | `baseline_vs_candidate` | jsonb | tidak | `'{}'::jsonb` | - |
| 8 | `backtest_run_ids` | jsonb | tidak | `'[]'::jsonb` | - |
| 9 | `risks` | jsonb | tidak | `'[]'::jsonb` | - |
| 10 | `status` | text | tidak | `'PROPOSED'::text` | - |
| 11 | `author` | text | tidak | `'hermes'::text` | - |
| 12 | `decided_by` | text | ya | - | - |
| 13 | `decided_at` | timestamp with time zone | ya | - | - |
| 14 | `decision_note` | text | ya | - | - |
| 15 | `strategy_version_id` | bigint | ya | - | FK→`strategy_versions`.`id` (NO ACTION) |
| 16 | `deployed_at` | timestamp with time zone | ya | - | - |
| 17 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_research_proposals_status`: `CREATE INDEX idx_research_proposals_status ON public.research_proposals USING btree (status, created_at)`

Constraint CHECK:
- `research_proposals_proposal_type_check`: `CHECK ((proposal_type = ANY (ARRAY['STRATEGY_PARAM'::text, 'NEW_STRATEGY'::text, 'EXPERIMENT'::text, 'OTHER'::text])))`
- `research_proposals_status_check`: `CHECK ((status = ANY (ARRAY['PROPOSED'::text, 'APPROVED'::text, 'REJECTED'::text, 'DEPLOYED'::text])))`

### `research_reports`: Laporan riset Hermes (PRD §12.3)

- Baris: **1** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('research_reports_id_seq'::regclass)` | PK |
| 2 | `title` | text | tidak | - | - |
| 3 | `report_type` | text | tidak | `'WEEKLY'::text` | - |
| 4 | `period_start` | timestamp with time zone | ya | - | - |
| 5 | `period_end` | timestamp with time zone | ya | - | - |
| 6 | `data_sources` | jsonb | tidak | `'{}'::jsonb` | - |
| 7 | `data_quality` | jsonb | tidak | `'{}'::jsonb` | - |
| 8 | `summary` | text | ya | - | - |
| 9 | `findings` | jsonb | tidak | `'[]'::jsonb` | - |
| 10 | `hypotheses` | jsonb | tidak | `'[]'::jsonb` | - |
| 11 | `recommendations` | jsonb | tidak | `'[]'::jsonb` | - |
| 12 | `baseline_vs_candidate` | jsonb | tidak | `'{}'::jsonb` | - |
| 13 | `risks` | jsonb | tidak | `'[]'::jsonb` | - |
| 14 | `author` | text | tidak | `'hermes'::text` | - |
| 15 | `status` | text | tidak | `'DRAFT'::text` | - |
| 16 | `supersedes_id` | bigint | ya | - | FK→`research_reports`.`id` (NO ACTION) |
| 17 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_research_reports_type`: `CREATE INDEX idx_research_reports_type ON public.research_reports USING btree (report_type, created_at)`

Constraint CHECK:
- `research_reports_report_type_check`: `CHECK ((report_type = ANY (ARRAY['WEEKLY'::text, 'DIAGNOSIS'::text, 'EXPERIMENT'::text, 'REVIEW'::text, 'OTHER'::text])))`
- `research_reports_status_check`: `CHECK ((status = ANY (ARRAY['DRAFT'::text, 'QA_REVIEW'::text, 'APPROVED'::text, 'SUPERSEDED'::text])))`

### `risk_decisions`: Keputusan risk gate + input (PRD §7)

- Baris: **0** · Retensi: 12 bulan

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('risk_decisions_id_seq'::regclass)` | PK |
| 2 | `order_id` | uuid | ya | - | FK→`orders`.`id` (NO ACTION) |
| 3 | `strategy_id` | text | ya | - | - |
| 4 | `decision` | text | tidak | - | - |
| 5 | `reason_code` | text | ya | - | - |
| 6 | `reason` | text | ya | - | - |
| 7 | `inputs` | jsonb | tidak | `'{}'::jsonb` | - |
| 8 | `limits_snapshot` | jsonb | tidak | `'{}'::jsonb` | - |
| 9 | `regime_label` | text | ya | - | - |
| 10 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_risk_decisions_created`: `CREATE INDEX idx_risk_decisions_created ON public.risk_decisions USING btree (created_at)`
- `idx_risk_decisions_order`: `CREATE INDEX idx_risk_decisions_order ON public.risk_decisions USING btree (order_id)`

Constraint CHECK:
- `risk_decisions_decision_check`: `CHECK ((decision = ANY (ARRAY['PASS'::text, 'REJECT'::text])))`

### `sessions`: Sesi login (cookie + CSRF)

- Baris: **342** · Retensi: expires_at + 30 hari

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | uuid | tidak | `gen_random_uuid()` | PK |
| 2 | `user_id` | bigint | tidak | - | FK→`users`.`id` (CASCADE) |
| 3 | `token_hash` | text | tidak | - | UQ |
| 4 | `csrf_token` | text | tidak | - | - |
| 5 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 6 | `expires_at` | timestamp with time zone | tidak | - | - |
| 7 | `last_seen_at` | timestamp with time zone | tidak | `now()` | - |
| 8 | `2fa_passed_at` | timestamp with time zone | ya | - | - |

Indeks:
- `sessions_token_hash_key`: `CREATE UNIQUE INDEX sessions_token_hash_key ON public.sessions USING btree (token_hash)`

### `settings`: Konfigurasi runtime JSONB (nilai aktif)

- Baris: **38** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `key` | text | tidak | - | PK |
| 2 | `value` | jsonb | tidak | - | - |
| 3 | `updated_at` | timestamp with time zone | tidak | `now()` | - |

Trigger:
- `settings_audit_trail`: `CREATE TRIGGER settings_audit_trail AFTER INSERT OR UPDATE ON public.settings FOR EACH ROW WHEN ((new.key <> 'ea_last_seen_at'::text)) EXECUTE FUNCTION fund2_settings_audit()`

### `settings_audit`: Audit perubahan konfigurasi

- Baris: **327** · Retensi: permanen · append-only

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('settings_audit_id_seq'::regclass)` | PK |
| 2 | `key` | text | tidak | - | - |
| 3 | `old_value` | jsonb | ya | - | - |
| 4 | `new_value` | jsonb | ya | - | - |
| 5 | `changed_by` | text | tidak | `'system'::text` | - |
| 6 | `source` | text | tidak | `'db'::text` | - |
| 7 | `changed_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_settings_audit_key`: `CREATE INDEX idx_settings_audit_key ON public.settings_audit USING btree (key, changed_at)`

### `shadow_runs`: Registry run shadow (PRD §9)

- Baris: **52** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('shadow_runs_id_seq'::regclass)` | PK |
| 2 | `run_id` | uuid | tidak | - | UQ |
| 3 | `strategy_id` | text | tidak | - | - |
| 4 | `strategy_version` | text | tidak | - | - |
| 5 | `symbol` | text | tidak | - | - |
| 6 | `timeframe` | text | tidak | - | - |
| 7 | `period_start` | timestamp with time zone | ya | - | - |
| 8 | `period_end` | timestamp with time zone | ya | - | - |
| 9 | `config` | jsonb | tidak | `'{}'::jsonb` | - |
| 10 | `cost_model` | jsonb | tidak | `'{}'::jsonb` | - |
| 11 | `metrics` | jsonb | tidak | `'{}'::jsonb` | - |
| 12 | `signal_count` | integer | tidak | `0` | - |
| 13 | `status` | text | tidak | `'RUNNING'::text` | - |
| 14 | `note` | text | ya | - | - |
| 15 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 16 | `completed_at` | timestamp with time zone | ya | - | - |
| 17 | `label` | text | tidak | `''::text` | - |

Indeks:
- `idx_shadow_runs_active_label`: `CREATE UNIQUE INDEX idx_shadow_runs_active_label ON public.shadow_runs USING btree (strategy_id, label) WHERE (status = 'RUNNING'::text)`
- `idx_shadow_runs_strategy`: `CREATE INDEX idx_shadow_runs_strategy ON public.shadow_runs USING btree (strategy_id, created_at)`
- `shadow_runs_run_id_key`: `CREATE UNIQUE INDEX shadow_runs_run_id_key ON public.shadow_runs USING btree (run_id)`

Constraint CHECK:
- `shadow_runs_status_check`: `CHECK ((status = ANY (ARRAY['RUNNING'::text, 'COMPLETED'::text, 'FAILED'::text])))`

### `shadow_signals`: Sinyal shadow + simulasi hasil

- Baris: **2** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('shadow_signals_id_seq'::regclass)` | PK |
| 2 | `run_id` | uuid | tidak | - | FK→`shadow_runs`.`run_id` (CASCADE) |
| 3 | `signal_ref` | text | ya | - | - |
| 4 | `strategy_id` | text | tidak | - | - |
| 5 | `strategy_version` | text | tidak | - | - |
| 6 | `label` | text | tidak | - | - |
| 7 | `symbol` | text | tidak | - | - |
| 8 | `timeframe` | text | tidak | - | - |
| 9 | `ts` | timestamp with time zone | tidak | - | - |
| 10 | `ref_bid` | numeric | ya | - | - |
| 11 | `ref_ask` | numeric | ya | - | - |
| 12 | `spread` | numeric | ya | - | - |
| 13 | `spread_median_15m` | numeric | ya | - | - |
| 14 | `regime_label` | text | ya | - | - |
| 15 | `regime_confidence` | numeric | ya | - | - |
| 16 | `side` | text | ya | - | - |
| 17 | `volume` | numeric | ya | - | - |
| 18 | `sl` | numeric | ya | - | - |
| 19 | `tp` | numeric | ya | - | - |
| 20 | `reason` | text | ya | - | - |
| 21 | `params_hash` | text | tidak | `''::text` | - |
| 22 | `code_commit` | text | ya | - | - |
| 23 | `is_simulation` | boolean | tidak | `true` | - |
| 24 | `sim_status` | text | tidak | `'FILLED'::text` | - |
| 25 | `sim_fill_price` | numeric | ya | - | - |
| 26 | `sim_cost_usd` | numeric | ya | - | - |
| 27 | `sim_exit_price` | numeric | ya | - | - |
| 28 | `sim_pnl_usd` | numeric | ya | - | - |
| 29 | `sim_exit_reason` | text | ya | - | - |
| 30 | `sim_opened_at` | timestamp with time zone | ya | - | - |
| 31 | `sim_closed_at` | timestamp with time zone | ya | - | - |
| 32 | `detail` | jsonb | tidak | `'{}'::jsonb` | - |
| 33 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_shadow_signals_run`: `CREATE INDEX idx_shadow_signals_run ON public.shadow_signals USING btree (run_id, created_at)`
- `idx_shadow_signals_strategy`: `CREATE INDEX idx_shadow_signals_strategy ON public.shadow_signals USING btree (strategy_id, label, ts)`

Constraint CHECK:
- `shadow_signals_side_check`: `CHECK ((side = ANY (ARRAY['BUY'::text, 'SELL'::text])))`
- `shadow_signals_sim_status_check`: `CHECK ((sim_status = ANY (ARRAY['FILLED'::text, 'REJECTED'::text, 'REGIME_BLOCKED'::text])))`

### `signals`: Keluaran decide() lintas mode

- Baris: **21** · Retensi: 12 bulan

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('signals_id_seq'::regclass)` | PK |
| 2 | `strategy_id` | text | tidak | - | - |
| 3 | `strategy_version` | text | ya | - | - |
| 4 | `symbol` | text | tidak | - | - |
| 5 | `timeframe` | text | tidak | - | - |
| 6 | `side` | text | ya | - | - |
| 7 | `order_intent` | jsonb | ya | - | - |
| 8 | `regime_label` | text | ya | - | - |
| 9 | `regime_confidence` | numeric | ya | - | - |
| 10 | `regime_version` | text | ya | - | - |
| 11 | `features` | jsonb | tidak | `'{}'::jsonb` | - |
| 12 | `reason` | text | ya | - | - |
| 13 | `source` | text | tidak | - | - |
| 14 | `status` | text | tidak | `'EMITTED'::text` | - |
| 15 | `reject_reason` | text | ya | - | - |
| 16 | `ref_type` | text | ya | - | - |
| 17 | `ref_id` | text | ya | - | - |
| 18 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_signals_strategy`: `CREATE INDEX idx_signals_strategy ON public.signals USING btree (strategy_id, created_at)`
- `idx_signals_symbol`: `CREATE INDEX idx_signals_symbol ON public.signals USING btree (symbol, created_at)`

Constraint CHECK:
- `signals_side_check`: `CHECK ((side = ANY (ARRAY['BUY'::text, 'SELL'::text])))`
- `signals_source_check`: `CHECK ((source = ANY (ARRAY['LIVE'::text, 'PAPER'::text, 'SHADOW'::text, 'BACKTEST'::text])))`
- `signals_status_check`: `CHECK ((status = ANY (ARRAY['EMITTED'::text, 'ACCEPTED'::text, 'REJECTED'::text, 'SUPERSEDED'::text])))`

### `strategies`: Lifecycle strategi (PRD §5.3)

- Baris: **4** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('strategies_id_seq'::regclass)` | PK |
| 2 | `strategy_id` | text | tidak | - | UQ |
| 3 | `name` | text | tidak | - | - |
| 4 | `description` | text | ya | - | - |
| 5 | `status` | text | tidak | `'DRAFT'::text` | - |
| 6 | `environment` | text | tidak | `'dev'::text` | - |
| 7 | `config` | jsonb | tidak | `'{}'::jsonb` | - |
| 8 | `allowed_regimes` | jsonb | tidak | `'[]'::jsonb` | - |
| 9 | `current_version` | text | ya | - | - |
| 10 | `enabled` | boolean | tidak | `false` | - |
| 11 | `circuit_breaker` | jsonb | tidak | `'{}'::jsonb` | - |
| 12 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 13 | `updated_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `strategies_strategy_id_key`: `CREATE UNIQUE INDEX strategies_strategy_id_key ON public.strategies USING btree (strategy_id)`

Constraint CHECK:
- `strategies_environment_check`: `CHECK ((environment = ANY (ARRAY['dev'::text, 'staging'::text, 'prod'::text])))`
- `strategies_status_check`: `CHECK ((status = ANY (ARRAY['DRAFT'::text, 'VALIDATING'::text, 'BACKTEST_APPROVED'::text, 'SHADOW'::text, 'PAPER'::text, 'LIVE_APPROVED'::text, 'LIVE'::text, 'DEGRADED'::text, 'DISABLED'::text, 'ARCHIVED'::text])))`

### `strategy_approvals`: Audit approval strategi (append-only)

- Baris: **8** · Retensi: permanen · append-only

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('strategy_approvals_id_seq'::regclass)` | PK |
| 2 | `strategy_version_id` | bigint | tidak | - | FK→`strategy_versions`.`id` (RESTRICT) |
| 3 | `stage` | text | tidak | - | - |
| 4 | `decision` | text | tidak | - | - |
| 5 | `reviewer` | text | tidak | - | - |
| 6 | `rationale` | text | ya | - | - |
| 7 | `evidence` | jsonb | tidak | `'{}'::jsonb` | - |
| 8 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_strategy_approvals_version`: `CREATE INDEX idx_strategy_approvals_version ON public.strategy_approvals USING btree (strategy_version_id, created_at)`

Constraint CHECK:
- `strategy_approvals_decision_check`: `CHECK ((decision = ANY (ARRAY['APPROVED'::text, 'REJECTED'::text])))`

Trigger:
- `strategy_approvals_append_only`: `CREATE TRIGGER strategy_approvals_append_only BEFORE DELETE OR UPDATE ON public.strategy_approvals FOR EACH ROW EXECUTE FUNCTION fund2_deny_mutation()`

### `strategy_versions`: Rilis strategi immutable (PRD §11.1)

- Baris: **3** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('strategy_versions_id_seq'::regclass)` | PK |
| 2 | `strategy_id` | text | tidak | - | FK→`strategies`.`strategy_id` (RESTRICT)<br>UQ |
| 3 | `version` | text | tidak | - | UQ |
| 4 | `code_commit_hash` | text | ya | - | - |
| 5 | `code_path` | text | ya | - | - |
| 6 | `params` | jsonb | tidak | `'{}'::jsonb` | - |
| 7 | `config_hash` | text | ya | - | - |
| 8 | `data_version` | text | ya | - | - |
| 9 | `backtest_report` | jsonb | ya | - | - |
| 10 | `walkforward_report` | jsonb | ya | - | - |
| 11 | `shadow_report` | jsonb | ya | - | - |
| 12 | `paper_report` | jsonb | ya | - | - |
| 13 | `risk_profile` | jsonb | ya | - | - |
| 14 | `status` | text | tidak | `'DRAFT'::text` | - |
| 15 | `change_reason` | text | ya | - | - |
| 16 | `created_by` | text | ya | - | - |
| 17 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 18 | `activated_at` | timestamp with time zone | ya | - | - |
| 19 | `deactivated_at` | timestamp with time zone | ya | - | - |

Indeks:
- `idx_strategy_versions_strategy`: `CREATE INDEX idx_strategy_versions_strategy ON public.strategy_versions USING btree (strategy_id, created_at)`
- `strategy_versions_strategy_id_version_key`: `CREATE UNIQUE INDEX strategy_versions_strategy_id_version_key ON public.strategy_versions USING btree (strategy_id, version)`

Constraint CHECK:
- `strategy_versions_status_check`: `CHECK ((status = ANY (ARRAY['DRAFT'::text, 'REVIEW'::text, 'APPROVED'::text, 'REJECTED'::text, 'SUPERSEDED'::text])))`

Trigger:
- `strategy_versions_immutable`: `CREATE TRIGGER strategy_versions_immutable BEFORE DELETE OR UPDATE ON public.strategy_versions FOR EACH ROW EXECUTE FUNCTION fund2_guard_strategy_version()`

### `system_events`: Event bus supervisor/audit (PRD §5.2, §18)

- Baris: **13** · Retensi: 12 bulan

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('system_events_id_seq'::regclass)` | PK |
| 2 | `event_type` | text | tidak | - | - |
| 3 | `severity` | text | tidak | `'INFO'::text` | - |
| 4 | `source` | text | tidak | - | - |
| 5 | `actor` | text | ya | - | - |
| 6 | `message` | text | tidak | - | - |
| 7 | `details` | jsonb | tidak | `'{}'::jsonb` | - |
| 8 | `correlation_id` | text | ya | - | - |
| 9 | `created_at` | timestamp with time zone | tidak | `now()` | - |

Indeks:
- `idx_system_events_severity`: `CREATE INDEX idx_system_events_severity ON public.system_events USING btree (severity, created_at)`
- `idx_system_events_type`: `CREATE INDEX idx_system_events_type ON public.system_events USING btree (event_type, created_at)`

Constraint CHECK:
- `system_events_severity_check`: `CHECK ((severity = ANY (ARRAY['INFO'::text, 'WARN'::text, 'ERROR'::text, 'CRITICAL'::text])))`

### `users`: Akun dashboard

- Baris: **12** · Retensi: permanen

| # | Kolom | Tipe | Null | Default | Kunci |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | bigint | tidak | `nextval('users_id_seq'::regclass)` | PK |
| 2 | `username` | text | tidak | - | UQ |
| 3 | `password_hash` | text | tidak | - | - |
| 4 | `created_at` | timestamp with time zone | tidak | `now()` | - |
| 5 | `role` | text | tidak | `'user'::text` | - |
| 6 | `totp_secret` | text | ya | - | - |
| 7 | `totp_enabled` | boolean | tidak | `false` | - |
| 8 | `totp_last_counter` | bigint | tidak | `'-1'::integer` | - |

Indeks:
- `idx_users_role`: `CREATE INDEX idx_users_role ON public.users USING btree (role)`
- `users_username_key`: `CREATE UNIQUE INDEX users_username_key ON public.users USING btree (username)`

Constraint CHECK:
- `users_role_check`: `CHECK ((role = ANY (ARRAY['admin'::text, 'agent'::text, 'user'::text, 'research'::text, 'qa'::text])))`

