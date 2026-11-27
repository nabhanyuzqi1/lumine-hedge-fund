#!/usr/bin/env python3
"""Generator DATA_DICTIONARY_v2.2.md dari DB live (read-only).

Sumber kebenaran struktur = database `fund2` (bukan dokumen). Skrip ini
membaca information_schema + pg_catalog, lalu menulis markdown.

Pemakaian (dari repo root, DB read-only):
    api/.venv/bin/python docs/gen_data_dictionary.py \
        --out docs/DATA_DICTIONARY_v2.2.md

Tidak menulis ke DB, tidak butuh kredensial tulis.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API_DIR))

import psycopg  # noqa: E402

# Peran tabel: diambil dari docs/SCHEMA_v2.2.md + PRD v2.2 §19.3/§19.4.
ROLES = {
    "users": ("Akun dashboard", "permanen"),
    "sessions": ("Sesi login (cookie + CSRF)", "expires_at + 30 hari"),
    "settings": ("Konfigurasi runtime JSONB (nilai aktif)", "permanen"),
    "settings_audit": ("Audit perubahan konfigurasi", "permanen"),
    "orders": ("Ledger order + state machine", "permanen"),
    "order_events": ("Append-only ledger transisi status (PRD §19.4)", "permanen"),
    "positions": ("Posisi broker hasil snapshot", "permanen"),
    "position_snapshots": ("Deret waktu state posisi/portofolio", "180 hari"),
    "candles": ("OHLC M1+ (partisi bulanan)", "24 bulan lalu arsip Parquet"),
    "liquidity_samples": ("Agregat spread 5 detik (partisi bulanan)", "90 hari"),
    "signals": ("Keluaran decide() lintas mode", "12 bulan"),
    "strategies": ("Lifecycle strategi (PRD §5.3)", "permanen"),
    "strategy_versions": ("Rilis strategi immutable (PRD §11.1)", "permanen"),
    "strategy_approvals": ("Audit approval strategi (append-only)", "permanen"),
    "backtest_runs": ("Registry semua percobaan backtest/WF (PRD §8.2)", "permanen"),
    "paper_runs": ("Registry run paper/replay/walk-forward", "permanen"),
    "paper_orders": ("Ledger paper trading", "permanen"),
    "paper_state": ("State runner paper (key-value)", "permanen"),
    "shadow_runs": ("Registry run shadow (PRD §9)", "permanen"),
    "shadow_signals": ("Sinyal shadow + simulasi hasil", "permanen"),
    "regime_observations": ("Label regime + confidence (PRD §6.4)", "12 bulan"),
    "risk_decisions": ("Keputusan risk gate + input (PRD §7)", "12 bulan"),
    "system_events": ("Event bus supervisor/audit (PRD §5.2, §18)", "12 bulan"),
    "reconciliation_runs": ("Snapshot broker vs ledger (PRD §15)", "permanen"),
    "deployment_records": ("Audit deployment/migrasi (PRD §17/§18)", "permanen"),
    "research_reports": ("Laporan riset Hermes (PRD §12.3)", "permanen"),
    "research_proposals": ("Usulan riset Hermes + keputusan", "permanen"),
    "bridge_commands": ("Antrean command reconciler ke EA (P1b)", "permanen"),
    "kill_switch_events": ("Audit kill-switch (v2.1 §5.7, append-only)", "permanen"),
    "audit_log": ("Audit aksi UI/API (aktor, aksi, target)", "permanen"),
    "login_failures": ("Rate-limit login + forensik", "90 hari"),
    "data_quality_runs": ("Hasil pemeriksaan kualitas data", "permanen"),
    "data_versions": ("Provenance dataset (checksum, rentang)", "permanen"),
    "degradation_events": ("Riwayat transisi degradation state", "permanen"),
    "degradation_state": ("State degradasi per strategi", "permanen"),
    "improvement_proposals": ("Usulan self-improve + approval", "permanen"),
    "llm_introspections": ("Introspeksi harian/per trade agent LLM", "permanen"),
    "paper_state": ("State runner paper (key-value)", "permanen"),
    "alembic_version": ("Versi migrasi aktif (Alembic)", "permanen"),
}

APPEND_ONLY = {"order_events", "strategy_approvals", "kill_switch_events", "settings_audit", "deployment_records"}


def col_rows(conn, schema="public"):
    return conn.execute(
        """
        select table_name, ordinal_position, column_name, data_type,
               character_maximum_length, is_nullable, column_default,
               is_identity
        from information_schema.columns
        where table_schema = %s
        order by table_name, ordinal_position
        """,
        (schema,),
    ).fetchall()


def pks(conn):
    rows = conn.execute(
        """
        select c.relname as table_name, a.attname as column_name
        from pg_index i
        join pg_class c on c.oid = i.indrelid
        join pg_namespace n on n.oid = c.relnamespace
        join pg_attribute a on a.attrelid = c.oid and a.attnum = any(i.indkey)
        where i.indisprimary and n.nspname = 'public'
        order by c.relname, a.attnum
        """
    ).fetchall()
    out: dict[str, list[str]] = {}
    for t, col in rows:
        out.setdefault(t, []).append(col)
    return out


def foreign_keys(conn):
    rows = conn.execute(
        """
        select tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name, rc.delete_rule
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on kcu.constraint_name = tc.constraint_name and kcu.table_schema = tc.table_schema
        join information_schema.constraint_column_usage ccu
          on ccu.constraint_name = tc.constraint_name and ccu.table_schema = tc.table_schema
        join information_schema.referential_constraints rc
          on rc.constraint_name = tc.constraint_name and rc.constraint_schema = tc.table_schema
        where tc.constraint_type = 'FOREIGN KEY' and tc.table_schema = 'public'
        order by tc.table_name, kcu.column_name
        """
    ).fetchall()
    return rows


def uniques(conn):
    rows = conn.execute(
        """
        select tc.table_name, string_agg(kcu.column_name, ', ' order by kcu.ordinal_position)
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on kcu.constraint_name = tc.constraint_name and kcu.table_schema = tc.table_schema
        where tc.constraint_type = 'UNIQUE' and tc.table_schema = 'public'
        group by tc.table_name, tc.constraint_name
        order by tc.table_name
        """
    ).fetchall()
    return rows


def indexes(conn):
    rows = conn.execute(
        """
        select tablename, indexname, indexdef
        from pg_indexes where schemaname = 'public'
        order by tablename, indexname
        """
    ).fetchall()
    return rows


def checks(conn):
    rows = conn.execute(
        """
        select rel.relname, con.conname, pg_get_constraintdef(con.oid)
        from pg_constraint con
        join pg_class rel on rel.oid = con.conrelid
        join pg_namespace n on n.oid = rel.relnamespace
        where n.nspname = 'public' and con.contype = 'c'
        order by rel.relname, con.conname
        """
    ).fetchall()
    return rows


def triggers(conn):
    rows = conn.execute(
        """
        select c.relname, t.tgname, pg_get_triggerdef(t.oid)
        from pg_trigger t
        join pg_class c on c.oid = t.tgrelid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and not t.tgisinternal
        order by c.relname, t.tgname
        """
    ).fetchall()
    return rows


def partitions(conn):
    rows = conn.execute(
        """
        select parent.relname, child.relname, pg_get_expr(child.relpartbound, child.oid)
        from pg_inherits i
        join pg_class parent on parent.oid = i.inhparent
        join pg_class child on child.oid = i.inhrelid
        join pg_namespace n on n.oid = parent.relnamespace
        where n.nspname = 'public'
        order by parent.relname, child.relname
        """
    ).fetchall()
    return rows


def counts(conn, tables):
    out = {}
    with conn.cursor() as cur:
        for t in tables:
            try:
                cur.execute(f'select count(*) from public."{t}"')
                out[t] = cur.fetchone()[0]
            except Exception as exc:  # pragma: no cover - diagnostik
                out[t] = f"err: {exc}"
    return out


def fmt_type(dt_, maxlen, is_identity):
    base = dt_
    if maxlen:
        base = f"{dt_}({maxlen})"
    if is_identity == "YES":
        base += " identity"
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/DATA_DICTIONARY_v2.2.md")
    ap.add_argument("--schema", default="public")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL tidak diset", file=sys.stderr)
        return 2

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("set default_transaction_read_only = on")
        version = conn.execute("select version_num from alembic_version").fetchone()
        tables = [
            r[0]
            for r in conn.execute(
                """
                select c.relname from pg_class c
                join pg_namespace n on n.oid = c.relnamespace
                where n.nspname = 'public' and c.relkind = 'r'
                order by 1
                """
            ).fetchall()
        ]
        part_names = {r[1] for r in partitions(conn)}
        cols = col_rows(conn, args.schema)
        pk = pks(conn)
        fks = foreign_keys(conn)
        uq = uniques(conn)
        idx = indexes(conn)
        chk = checks(conn)
        trg = triggers(conn)
        part = partitions(conn)
        nrows = counts(conn, tables)

    by_table: dict[str, list] = {}
    for r in cols:
        by_table.setdefault(r[0], []).append(r)
    fk_by: dict[str, list] = {}
    for t, col, rt, rcol, rule in fks:
        fk_by.setdefault(t, []).append((col, rt, rcol, rule))
    uq_by: dict[str, list] = {}
    for t, cols_ in uq:
        uq_by.setdefault(t, []).append(cols_)
    idx_by: dict[str, list] = {}
    for t, name, ddl in idx:
        if name in {f"{t}_pkey"}:
            continue
        idx_by.setdefault(t, []).append((name, ddl))
    chk_by: dict[str, list] = {}
    for t, name, ddl in chk:
        chk_by.setdefault(t, []).append((name, ddl))
    trg_by: dict[str, list] = {}
    for t, name, ddl in trg:
        trg_by.setdefault(t, []).append((name, ddl))
    part_by: dict[str, list] = {}
    for p, c, bound in part:
        part_by.setdefault(p, []).append((c, bound))

    now = dt.datetime.now(dt.timezone.utc).astimezone()
    lines: list[str] = []
    a = lines.append
    a("# Data Dictionary: Fund2 v2.2")
    a("")
    a("| | |")
    a("| --- | --- |")
    a(f"| Digenerate | {now.strftime('%Y-%m-%d %H:%M %Z')} |")
    a("| Sumber | DB live `fund2` @ 127.0.0.1:5433, **read-only** |")
    a(f"| Migrasi aktif (Alembic) | `{version[0] if version else 'unknown'}` |")
    a(f"| Jumlah relasi (tabel + partisi) | {len(tables)} |")
    a("| Generator | `docs/gen_data_dictionary.py` |")
    a("")
    a("Dokumen ini dihasilkan ulang dari katalog PostgreSQL, bukan diketik manual:")
    a("struktur yang tertulis di sini adalah struktur yang benar-benar ada di DB.")
    a("Peran tabel dan kebijakan retensi diambil dari `docs/SCHEMA_v2.2.md`")
    a("(keputusan retensi/partisi berbasis volume aktual).")
    a("")
    a("Legenda: **PK** primary key, **FK** foreign key, **UQ** unique, **AO** append-only (trigger),")
    a("**IDX** indeks non-PK.")
    a("")
    a("## 1. Ringkasan tabel")
    a("")
    a("| Tabel | Peran | Baris | PK | Retensi |")
    a("| --- | --- | ---: | --- | --- |")
    for t in tables:
        role, ret = ROLES.get(t, ("(lihat migrasi / kode)", "-"))
        if t in part_names:
            role = role if role != "(lihat migrasi / kode)" else "partisi"
        pk_ = ", ".join(pk.get(t, [])) or "-"
        a(f"| `{t}` | {role} | {nrows[t]:,} | {pk_} | {ret} |")
    a("")
    a("## 2. Partisi & retensi")
    a("")
    if part_by:
        a("| Tabel induk | Partisi | Bound |")
        a("| --- | --- | --- |")
        for p, children in sorted(part_by.items()):
            for c, bound in children:
                a(f"| `{p}` | `{c}` | `{bound}` |")
    else:
        a("Tidak ada tabel terpartisi di schema ini.")
    a("")
    a("Kebijakan retensi (dari `SCHEMA_v2.2.md`): partisi bulanan diganti arsip Parquet")
    a("sebelum drop; `order_events`, `strategy_approvals`, `kill_switch_events` tidak pernah")
    a("dihapus (append-only, kebutuhan audit).")
    a("")
    a("## 3. Kamus kolom per tabel")
    a("")
    for t in tables:
        role, ret = ROLES.get(t, ("(lihat migrasi / kode)", "-"))
        a(f"### `{t}`: {role}")
        a("")
        flags = []
        if t in APPEND_ONLY:
            flags.append("append-only")
        if t in part_by:
            flags.append("terpartisi")
        a(f"- Baris: **{nrows[t]:,}** · Retensi: {ret}" + (f" · {' · '.join(flags)}" if flags else ""))
        a("")
        a("| # | Kolom | Tipe | Null | Default | Kunci |")
        a("| ---: | --- | --- | --- | --- | --- |")
        for r in by_table.get(t, []):
            _, pos, name, dtype, maxlen, nullable, default, ident = r
            key = []
            if name in pk.get(t, []):
                key.append("PK")
            for col, rt, rcol, rule in fk_by.get(t, []):
                if col == name:
                    key.append(f"FK→`{rt}`.`{rcol}` ({rule})")
            for cols_ in uq_by.get(t, []):
                if name in [x.strip() for x in cols_.split(",")]:
                    key.append("UQ")
            a(
                f"| {pos} | `{name}` | {fmt_type(dtype, maxlen, ident)} | "
                f"{'ya' if nullable == 'YES' else 'tidak'} | "
                f"{('`' + str(default) + '`') if default not in (None, '') else '-'} | "
                f"{'<br>'.join(key) or '-'} |"
            )
        a("")
        if idx_by.get(t):
            a("Indeks:")
            for name, ddl in idx_by[t]:
                a(f"- `{name}`: `{ddl}`")
            a("")
        if chk_by.get(t):
            a("Constraint CHECK:")
            for name, ddl in chk_by[t]:
                a(f"- `{name}`: `{ddl}`")
            a("")
        if trg_by.get(t):
            a("Trigger:")
            for name, ddl in trg_by[t]:
                a(f"- `{name}`: `{ddl}`")
            a("")

    out = Path(args.out)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"ditulis: {out} ({out.stat().st_size} bytes, {len(tables)} tabel)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
