# Lumine — Checkpoint 20 Aug 2026

> Auto-generated agent checkpoint. Commit terakhir: `1f4dbcc`.
> Branch: `dev` (push trigger CI + auto-deploy). CI hijau (32353751247 success).
> Production: deploy 09:26:52 UTC+7, EA v4.13 live, worker sehat.

## Cara melanjutkan (untuk sesi berikutnya)

```bash
cd C:/Users/nabha/OneDrive/Documents/GitHub/lumine-hedge-fund
git checkout dev && git pull
# Test cepat sebelum kerja:
cd backend && env -u PYTHONPATH .venv/Scripts/python.exe -m pytest tests/unit tests/contract -q
cd ../frontend && node node_modules/typescript/bin/tsc --noEmit && npx vitest run
```

## Status PHASE (Implementation Order ara #36)

| Phase | Fokus | Status |
|---|---|---|
| 1 | Critical Trading (semantic exec, BE/trailing/cutloss deterministic, lineage) | ✅ selesai |
| 2 | Automated Learning (backtest scheduler, research DB, learning agent, memory) | ⚠️ **sisa**: learning agent + persistent memory |
| 3 | AI Decision (CIO confidence, profile-aware, realtime context, routing, debate) | ✅ selesai |
| 4 | Realtime (news SSE, DXY terminal, account/position context, SSE observability) | ✅ selesai |
| 5 | Research UI (paper trading page, paper-vs-real, research dashboard) | ⚠️ **sisa**: dashboard lanjutan (charts/insight) |
| 6 | UI/UX (System Config, tooltip, committee summary, terminal, responsive) | ⚠️ **sisa**: System Config unsaved-state + responsive tablet/mobile |
| 7 | Cleanup (hapus What-If, dead code, placeholder, regression) | ✅ selesai |

## Status TASK terbaru (19-20 Aug 2026)

| Task | Status | Commit | Verifikasi live |
|---|---|---|---|
| P0 dashboard fix (data ilang-muncul saat WS gagal) | ✅ | `7a2a248` | keepPreviousData + throw; TS 0 |
| P1 CIO confidence (analyst_alignment → prompt) | ✅ | `7641917` | CI green |
| A1 data tak boleh Null → LLM: yield FRED real, mt5_account lengkap, market_state | ✅ | `83f83cb` | `lumine:yields` = {us_10y:4.71, us_2y:4.19} |
| A2 side ambiguity → SideBadge konsisten BUY/SELL | ✅ | `83f83cb` | terminal + order-detail |
| A3 SL/TP sesuai profil (clamp ATR) + posisi lama auto SL/TP | ✅ | `83f83cb` | position_monitor init SL |
| A4 Support/Resistance multi-TF (1m/5m/15m/1h) → analyst | ✅ | `83f83cb` | `support_resistance` di variables |
| A5 entry area terbaik (S/R pullback) + reason LLM di detail order | ✅ | `83f83cb` | migration c02228f00018 `ai_reason` + card AI Decision Reason |
| A6 berita geopolitik (perang/konflik) RSS → analyst | ✅ | `960d1ad` `8c06761` `1f4dbcc` | 8 headline live (Kyiv/Iran/Israel), defusedxml fallback |
| CI fix: openapi stale + bandit B608 | ✅ | `2212dff` `726fcf9` | CI hijau |

## SISA TASK (urutan kerja berikutnya)

1. **A7 — DXY bareng pair lain di terminal + UI research title konsisten**
   - `dxy-badge.tsx` saat ini terpisah di header terminal → pindah ke QuotePanel
     (bareng pair EURUSD/USDJPY dll). Research page title ikut pola halaman lain
     (title + description + status badge).
2. **P2-sisa — Learning agent + persistent memory**
   - `backtest/scheduler.py` sudah ada (6 jam → digest). Yang belum: agent yang
     membaca `backtest_learnings` + trade outcomes → proposal improvement loop.
3. **P5-sisa — Research dashboard lanjutan**
   - research.tsx sudah punya summary card paper-vs-real → tambah charts
     (equity curve PAPER vs REAL overlay) + insight.
4. **P6-sisa — System Config unsaved-state + responsive tablet/mobile**
   - superadmin ConfigTab: dirty-state indicator + save feedback; audit
     responsive di 768px/1024px.

## Kredensial & konvensi (jangan commit secret!)

- VPS `root@166.88.227.177`, key `~/.ssh/id_lumine_deploy`, `-o BatchMode=yes`
- Backend local: `env -u PYTHONPATH .venv/Scripts/python.exe` (venv global korup)
- ruff/bandit/pytest pakai venv backend; frontend: tsc + vitest
- CI: `uv run ruff check src tests`, `uv run bandit -r src -ll -q`, contract test
  cek openapi.yaml stale → regenerate `python -m scripts.generate_openapi`
- EA/MT5: polling 1s (JANGAN WebSocket), User-Agent `LumineEA/4.13`,
  hostname `http://lumine.biz.id` (bukan IP — whitelist non-DNS = 4014)
- Migrasi baru: `backend/alembic/versions/c02228f00018_*.py` (terakhir)
- Prompt satu sumber: root `docs/prompts/` → copy ke `backend/docs/prompts/`
  (CI drift guard) + update hash di `registry.yaml`
- **NEVER commit API keys/tokens/passwords — [REDACTED]**
