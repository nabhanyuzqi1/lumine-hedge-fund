# Formulir Approval Rilis: Fund2 v2.2

Kartu: **t_f2v22a18** · Artefak wajib Lampiran B ("owner release approval") · Disusun: hf-ceo
Tanggal: 26 Nov 2026 · **Status: BELUM DIBERIKAN: jawaban sah saat ini adalah NO-GO**

Dokumen ini adalah formulir yang harus diisi owner. Agent tidak berhak mengisinya, dan tidak ada
approval yang dianggap sah bila hanya berupa asumsi, lisan tanpa catatan, atau persetujuan lama yang
tidak menyebut lingkup.

## 1. Lingkup yang dimintakan persetujuan

Tiga keputusan terpisah. Satu tidak menggantikan yang lain:

| Kode | Keputusan | Konsekuensi bila disetujui |
| --- | --- | --- |
| **G2-a** | Melanjutkan rilis v2.2 untuk **paper/P9 dan UAT** (tanpa uang nyata) | Aman: tidak ada order broker live |
| **G2-b** | **Canary live** (uang nyata, modal minimum) | Butuh D1, approval tertulis, guardrail final, drill rollback |
| **G3** | **Live penuh / naik modal** | Butuh canary lulus + laporan stabilisasi |

Status sekarang: **G2-a = GO** (fase dokumentasi & paper), **G2-b = NO-GO**, **G3 = NO-GO**.

## 2. Daftar periksa prasyarat (diperbarui 26 Nov 2026)

| # | Prasyarat | Bukti yang diterima | Status 26 Nov |
| --- | --- | --- | --- |
| A-01 | Semua kartu engineering v2.2 selesai & terverifikasi | laporan verifikasi + board | **SEBAGIAN** (`t_f2llm4` blocked; `t_a172bb7b`, `t_d3ab9839` berjalan) |
| A-02 | P9 lulus (20 hari kerja, 100 trade, PF ≥ 1,3, DD ≤ 5%) | `eval_gate_paper.py` + laporan QA | **BELUM** (3 hari, 30 trade, PF 1,09) |
| A-03 | UAT owner lulus | berita acara UAT | **BELUM** |
| A-04 | QA sign-off rilis | kartu QA + release checklist | **BELUM** |
| A-05 | D1 terisi owner (modal live + batas kerugian absolut) | `KEPUTUSAN_OWNER.md` bagian baru + chat | **BELUM (DEFER)** |
| A-06 | Approval live tertulis owner | pernyataan eksplisit, terpisah dari H1 | **BELUM** |
| A-07 | Guardrail G-01..G-06, G-11, G-12 disetujui & terpasang | tabel §3 `PRASYARAT_LIVE_v2.2.md` diperbarui + bukti query | **BELUM** (drift masih ada; menunggu `t_d3ab9839`) |
| A-08 | Drill rollback aplikasi penuh lulus | laporan drill langkah 1-10 | **BELUM** |
| A-09 | Drill kill-switch oleh owner (aktivasi + release) | baris `kill_switch_events` dengan aktor owner | **BELUM** |
| A-10 | Pipeline alert sehat, F1/F2 ditutup | uji `--send-test` 4x + bukti terima | **SEBAGIAN** (mitigasi restart; alert restart 1x saat pytest) |
| A-11 | Release artifact ter-freeze dan ter-tag | tag `fund2-v2.2-rc<N>` pada commit bersih + checksum | **BELUM** (tree kotor, belum ada tag) |
| A-12 | Backup pre-release | `fund2_backup.sh pre-deploy` sukses + offsite | **BELUM** (dijalankan di window) |
| A-13 | Pentest + pytest penuh di release window | log hasil di kartu rilis | **SEBAGIAN** (pytest 1.347 lulus/1 gagal drift; pentest perlu rerun) |
| A-14 | Persetujuan risiko residual (D14) | tanda tangan pada risk policy + threat model | **BELUM** |

Aturan: satu baris BELUM = **NO-GO**. Pengecualian hanya sah bila tertulis, menyebut baris mana yang
dikecualikan, dan ditandatangani owner (pola H1).

## 3. Yang diminta dari owner (isi dan kirim balik)

### 3.1 Angka guardrail final (A-07)

Saat ini runtime lebih longgar dari kebijakan (rincian di `PRASYARAT_LIVE_v2.2.md` §3). Kartu
`t_d3ab9839` sedang menyiapkan angka final. Yang dibutuhkan dari owner: **menyetujui angka final**
untuk G-01 volume maksimum, G-02 order/menit, G-03 DD harian, G-04 DD total, G-05 FAILED beruntun,
G-06 EA offline, G-12 tick basi; atau menyatakan angka alternatif.

### 3.2 Penerimaan risiko residual (A-14, D14)

Enam risiko residual di `THREAT_MODEL_v2.2.md` §7 (RR-1..RR-6), teratas: kalibrasi biaya vs HFM belum
terbukti penuh (rating Tinggi) dan host tunggal tanpa HA.

### 3.3 D1: modal live dan batas kerugian absolut (A-05)

Wajib angka dari owner, tidak ada default di PRD:

- Modal live yang dialokasikan: `________` USD
- Batas kerugian absolut (stop total, bukan persentase): `________` USD
- Batas kerugian harian absolut: `________` USD
- Instrumen yang diizinkan: `XAUUSD` / `BTCUSD` (coret yang tidak dipakai)

### 3.4 Approval live tertulis (A-06)

Kalimat yang sah, misalnya:

> "Saya menyetujui canary live Fund2 v2.2 dengan modal maksimum `<X>` USD dan batas kerugian absolut
> `<Y>` USD, untuk strategi `<nama versi>`, selama `<N>` hari kerja, dengan syarat A-01..A-14 terpenuhi.
> Saya menerima risiko residual RR-1..RR-6."

## 4. Tanda tangan

| Keputusan | Nama | Tanggal | Pernyataan | Status |
| --- | --- | --- | --- | --- |
| G2-a paper/P9 | owner | - | - | **terbuka (disarankan GO)** |
| Angka guardrail final | owner | - | - | **BELUM** |
| Risiko residual (D14) | owner | - | - | **BELUM** |
| D1 modal & batas kerugian | owner | - | - | **BELUM (DEFER)** |
| G2-b canary live (A-06) | owner | - | - | **BELUM** |
| G3 live penuh | owner | - | - | **BELUM** |

Tanda tangan digital: balasan chat kantor dari akun owner yang menyebut kode keputusan di atas,
disimpan sebagai komentar di kartu rilis. Tidak ada tanda tangan yang sah dari agent mana pun.

## 5. Konsekuensi bila formulir ini kosong

- Rilis tetap pada status **NO-GO live** (`RELEASE_NOTES_v2.2.md` §5).
- Tidak ada deploy ke akun live, tidak ada perubahan `FUND2_ENV=live`, tidak ada canary "modal kecil".
- Paper/P9 boleh lanjut karena tidak memakai uang nyata.

## 6. Riwayat keputusan owner yang sudah sah (referensi)

| Tanggal | Kode | Isi | Dokumen |
| --- | --- | --- | --- |
| 2026-11-21 | Baseline | "SETUJU SEMUA" A1-A12, B1-B4, C1-C3, D2-D16; D1 DEFER | `KEPUTUSAN_OWNER.md` §E |
| 2026-11-22 | F1/F2 | Multipair XAUUSD+BTCUSD; live tetap OFF | `KEPUTUSAN_OWNER.md` §F |
| 2026-11-22 | G1 | Full LLM trading dengan 6 syarat pengaman | `KEPUTUSAN_OWNER.md` §G |
| 2026-11-23 | H1 | Buka gate P2 dengan pengecualian tertulis; kartu live ditahan | `KEPUTUSAN_OWNER.md` §H |

H1 **bukan** approval live. Approval live adalah dokumen ini, terpisah dan bertanggal.

## 7. Log permintaan approval

| Tanggal | Kartu | Yang dimintakan | Kanal | Hasil |
| --- | --- | --- | --- | --- |
| 2026-11-26 07:28 WIB | `t_8fe95620` | **G2-a** (paper/P9 + UAT lanjut, tanpa uang nyata); G2-b dan G3 tidak dimintakan karena gate belum terbuka | Kantor DeskRPG (pertanyaan berchoice) | **Tidak ada user tersedia untuk menjawab** (`unattended: true`). Formulir tetap kosong |

Keputusan gate yang ditetapkan CEO pada jendela yang sama: **NO-GO canary/live, GO bersyarat paper/UAT**, lihat `docs/KEPUTUSAN_GATE_RILIS_v2.2.md`.

Log ini mencatat percobaan, bukan persetujuan. Baris tanda tangan §4 tetap kosong sampai owner menulis jawabannya.

