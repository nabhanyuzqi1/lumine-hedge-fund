# Model Chain Worker Fund (keputusan owner, 24 Nov 2026)

Owner menetapkan pengembangan Lumine Fund memakai lineup model relay
(genomeprobe.cloud, paket 2 hari s/d 26 Nov 2026 06:52 WIB) dengan
**sequential fallback** berbasis kegagalan teknis.

## Spesifikasi owner (urutan penuh per role)

- **CEO / Backend / Frontend**: primary GPT-6 Astra
- **QA / DevOps**: primary Claude Opus 5.5
- **UI/UX**: primary Claude Sonnet 5.5
- Tiap role: 20 model relay sesuai urutan owner, ditutup **Lucif → Lucif-Flash**
  (paling akhir, sesuai permintaan owner; keduanya terverifikasi ada di provider lucif).
- Aturan fallback: timeout / 429 / 5xx / provider unavailable → fallback berikutnya;
  context limit → model berkapasitas memadai; invalid response → retry terbatas lalu
  fallback; semua gagal → task failed. Fallback TIDAK boleh karena jawaban tidak disukai.
- Urutan disimpan di **config tiap agent**, bukan hardcode di kode.

## Kendala relay (terverifikasi 24 Nov)

- **1 key = 1 model pin.** Semua profil berbagi 1 key → tidak bisa 6 primary
  berbeda bersamaan. Ganti model dibatasi **1x per 10 jam**.
- Penolakan "model tidak aktif" = HTTP 400, **tidak memicu fallback** Hermes
  (fallback hanya untuk 429/overload/koneksi/auth).
- Kesimpulan: spesifikasi penuh per-role belum bisa jalan di relay ini.

## Konfigurasi yang LIVE sekarang (mode `shared`)

- 6 profil hf-* : primary = `gp-claude-opus-5.5` (model yang di-pin relay,
  keputusan owner 24 Nov 2026),
  chain = `lucif` → `lucif-flash` (fallback 429/5xx/koneksi/auth, termasuk
  saat paket relay habis 26 Nov — transisi otomatis ke lucif).
- Config: `~/.hermes/profiles/hf-*/config.yaml` (`model.*` + `fallback_providers`),
  key di `~/.hermes/profiles/hf-*/.env` (tidak pernah ditulis di chat).

## Rotasi model (1x/10 jam)

Saat lock lebar, ganti pin ke model pilihan owner (mis. GPT-6 Astra):

    python3 scripts/apply_model_chain.py --mode shared --primary gp-gpt-6-astra

Seluruh 6 profil lalu memakai model itu; chain tetap lucif → lucif-flash.

## Saat relay membebaskan multi-model (atau relay baru)

Terapkan spesifikasi penuh owner sekali jalan:

    python3 scripts/apply_model_chain.py --mode full --dry-run   # pratinjau
    python3 scripts/apply_model_chain.py --mode full

Script: `scripts/apply_model_chain.py` (urutan per-role tertanam di dalamnya).
