# Sprint Plan — Lumine Fund v2 (Fund Core + End-to-End)

Sumber: `PRD_v2.1_Fund_Core.md` + `PRD_v2.2_End_to_End.md`.
Board: DeskRPG office-fund (kanban `deskrpg-da0b82b192024c709c4e12675baf3afe`).
Total: 58 kartu FUND2. Urutan fase dikunci via parent links (kartu fase berikutnya tidak bisa `ready` sebelum DoD gate fase sebelumnya `done`).

## P0 — Fondasi & Pengukuran (2 hari)
| Kartu | Assignee | Isi |
| --- | --- | --- |
| t_f2p0a1 | hf-devops | Perekaman spread/slippage HFM (parquet+log), jalan terus sampai P5 |
| t_f2p0a2 | hf-qa | Harness latensi T0..T4 skeleton |
| t_f2p0a3 | hf-ceo | Keputusan owner atas semua angka [USULAN] → docs/KEPUTUSAN_OWNER.md |
| t_f2p0a4 | hf-backend | EA v0: heartbeat + tick batch + HMAC ke endpoint dummy |
| t_f2co_p0 | hf-ceo | DoD gate P0 |

## P1a — Core Backend (5 hari)
| Kartu | Assignee | Isi |
| --- | --- | --- |
| t_4169d6d9 | hf-backend | API core: auth + state machine + event log + risk gate + bridge endpoint (status: review) |
| t_7694b38c | hf-devops | EA bridge baru + service native (status: blocked — nunggu whitelist MT5 manual) |
| t_f2p1a1 | hf-devops | Ingest tick: ring buffer + flush parquet + candle M1 + liquidity_samples |
| t_f2p1a2 | hf-backend | Kill-switch manual + auto-trigger + halt persisten |

## P1b — UI + Strategi + Reconciler (5 hari)
| Kartu | Assignee | Isi |
| --- | --- | --- |
| t_9c9f4b14 | hf-frontend | UI 4 halaman standar awwwards (status: review) |
| t_f2p1b1 | hf-backend | Reconciler: STUCK >60s + snapshot reconnect + orphan adopt/close |
| t_f2p1b2 | hf-backend | Strategi rule #1 breakout London + filter spread (skill + decide()) |
| t_f2p1b3 | hf-devops | Telegram alert: kill-switch, EA offline, rekap harian |
| t_f2p1b4 | hf-qa | QA: disconnect 10× + kill-switch + UI mobile + keamanan dasar |
| t_55fb2608 | hf-qa | QA paritas core |
| t_f2co_p1 | hf-ceo | DoD gate P1a+P1b |
| t_f2own1 | hf-ceo | Owner approval: risk parameter & 14 keputusan wajib (PRD v2.2 §29) |

## P2 — Data & Riset (6 hari)
| Kartu | Assignee | Isi |
| --- | --- | --- |
| t_f2p2a1 | hf-devops | Skill data-crawler Dukascopy → parquet + candles, validasi gap/duplikat |
| t_f2p2a2 | hf-backend | Backtest engine event-driven + biaya terkalibrasi |
| t_f2p2a3 | hf-backend | Walk-forward runner + backtest_runs registry |
| t_f2p2a4 | hf-backend | Strategi #2 mean reversion |
| t_f2p2a5 | hf-qa | QA paritas backtest vs paper |
| t_f2p2a6 | hf-backend | Format skill strategi final + template strategy-author |
| t_f2co_p2 | hf-ceo | DoD gate P2 |

## v2.2 — Lapisan keselamatan & kualitas strategi
| Kartu | Assignee | Isi |
| --- | --- | --- |
| t_f2v22a1 | hf-backend | Strategy Isolation Supervisor + circuit breaker |
| t_f2v22a2 | hf-backend | Market Regime Detection deterministic |
| t_f2v22a3 | hf-backend | Portfolio Risk Manager + stress test |
| t_f2v22a4 | hf-backend | Shadow Strategy |
| t_f2v22a5 | hf-backend | Degradation Detection NORMAL→WATCH→DEGRADED→HALTED |
| t_f2v22a6 | hf-backend | Strategy Versioning, Approval & Rollback |
| t_f2v22a7 | hf-backend | Hermes Research Intelligence read-only + anti prompt-injection |
| t_f2v22a8 | hf-devops | Disaster Recovery: backup harian + restore drill + RTO/RPO |
| t_f2v22a9 | hf-devops | Security: Argon2id, 2FA, RBAC, CSRF, rate limit, secret scan |
| t_f2v22a10 | hf-devops | Observability & alerting SEV-1..SEV-4 |
| t_f2v22a11 | hf-devops | Data pipeline: kualitas data + append-only ledger guard |
| t_f2v22a12 | hf-frontend | UI Operations & Recovery + UX safety |
| t_f2v22a13 | hf-qa | Test strategy lengkap (unit/property/integration/e2e/fault/security) |
| t_f2v22a14 | hf-qa | Paper trading 20 hari kerja + 100 trade + release candidate |
| t_f2v22a15 | hf-devops | Canary live terbatas (butuh owner approve tertulis) |
| t_f2v22a16 | hf-ceo | General release + 7 hari stabilisasi |
| t_f2v22a17 | hf-ceo | Release checklist + rollback plan + incident playbook |
| t_f2v22a18 | hf-ceo | Artefak wajib rilis (threat model, ADR, data dictionary, protocol spec) |
| t_f2v22a19 | hf-backend | Backtest data provenance + deteksi bias + reproducibility |
| t_f2v22a20 | hf-ceo | Risk register 14 item + threat model |
| t_f2v22a21 | hf-backend | Migrasi skema lengkap 24 tabel (v2.2 19.3) + order_events append-only |
| t_f2v22b1 | hf-qa | Load/soak test + incident simulation |
| t_f2v22b2 | hf-devops | Runbook + alert kritis ke owner |

## P3 — ML/RL (opsional, paralel, butuh approve owner)
| Kartu | Assignee | Isi |
| --- | --- | --- |
| t_f2p3a1 | hf-backend | Feature store + pipeline training offline (ML) |
| t_f2p3a2 | hf-backend | RL eksperimental (stable-baselines3) |

## P4 — LLM & Ops (4 hari)
| Kartu | Assignee | Isi |
| --- | --- | --- |
| t_f2p4a1 | hf-backend | Self-improvement loop mingguan |
| t_f2p4a2 | hf-devops | Cron harian rekap P&L + kesehatan bridge + anomali |
| t_f2p4a3 | hf-backend | Alur approve laporan → deploy flag enabled |
| t_f2p4a4 | hf-qa | QA garis merah LLM (penetration sederhana) |
| t_f2co_p4 | hf-ceo | DoD gate P4 |

## P5 — Cutover (3 hari)
| Kartu | Assignee | Isi |
| --- | --- | --- |
| t_f2p5a1 | hf-qa | QA paritas v1 vs v2 + latensi + restore + 7 gerbang go-live |
| t_f2p5a2 | hf-devops | Pindah domain fund.lumine.biz.id ke v2 (jam pasar sepi) |
| t_f2p5a3 | hf-devops | Pantau intensif + arsip v1 setelah 7 hari stabil |
| t_f2co_p5 | hf-ceo | DoD gate cutover final |

## Aturan eksekusi
- Fase tidak naik sebelum DoD gate fase sebelumnya `done` (dikunci via task_links parent).
- P3 ML/RL tidak boleh memblokir P4/P5; mulai hanya jika P2 selesai + owner setuju.
- Paper trading 20 hari kerja berjalan paralel setelah P1b; cutover menunggu gerbang paper, bukan dipaksa jadwal.
- Tidak ada live tanpa persetujuan tertulis owner (t_f2own1 + t_f2v22a15).
