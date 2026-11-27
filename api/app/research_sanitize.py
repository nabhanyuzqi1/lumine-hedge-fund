"""Sanitasi data riset Hermes (PRD v2.2 §12.4).

Data pasar, komentar, file, log, dan output eksternal dianggap data
tidak tepercaya, bukan instruksi. Modul ini menyediakan:

- redact(): buang nilai key sensitif (token/secret/password/api key)
  dari struktur output tool secara rekursif.
- scan_injection(): deteksi pola instruksi/perintah di dalam teks data.
  Hasilnya adalah TEMUAN yang dilaporkan, tidak pernah dieksekusi.
- is_exec_injection(): pola eksekusi (perintah shell, aksi order,
  sabotase kill-switch) -> tool menolak input yang mengandungnya.
"""
from __future__ import annotations

import re

# Key yang nilainya selalu diganti "***" pada output tool (defence in depth;
# tool riset memang tidak pernah membaca tabel settings, tapi payload bebas
# dari order_events bisa membawa field apa pun).
_SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|credential|authorization|cookie)",
    re.I,
)

_INSTRUCTION_PATTERNS = (
    r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules|messages)",
    r"disregard\s+(all\s+)?(previous|prior|above|earlier)",
    r"(you\s+are|act\s+as|pretend\s+(to\s+be|you\s+are))\s+(now\s+)?(a|an)\s+\w",
    r"system\s+prompt",
    r"</?\s*(research_data|market_data|untrusted)\s*>",
    r"(reveal|print|show|dump|repeat)\s+(your\s+)?(system\s+prompt|instructions|secrets?|credentials)",
    r"new\s+(instructions?|rules?)\s*:",
    r"assistant\s*:|system\s*:\s",
)

# Pola yang TOLERAN kosong: input argumen tool yang mengandung pola ini
# ditolak (422) karena berusaha mengeksekusi sesuatu, bukan menyimpan data.
_EXEC_PATTERNS = (
    r"\b(sudo|rm\s+-rf|mkfs|wget|curl|nc\s+-|bash\s+-c|sh\s+-c|python\s+-c)\b",
    r"(place|send|submit|open|close|cancel|modify)\s+(a\s+)?(order|trade|position)",
    r"(disable|deactivate|release|bypass|turn\s+off)\s+(the\s+)?(kill.?switch|risk\s+gate|risk\s+settings)",
    r"(activate|enable)\s+(the\s+)?(strategy|live\s+trading|kill.?switch)",
    r"\bDROP\s+TABLE\b|\bDELETE\s+FROM\b|\bINSERT\s+INTO\b|\bUPDATE\s+\w+\s+SET\b",
)

_INSTRUCTION_RE = [re.compile(p, re.I) for p in _INSTRUCTION_PATTERNS]
_EXEC_RE = [re.compile(p, re.I) for p in _EXEC_PATTERNS]

_MAX_FINDINGS = 20
_SNIPPET_LEN = 80


def redact(obj):
    """Ganti nilai key sensitif dengan '***' secara rekursif (JSON-safe)."""
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if _SECRET_KEY_RE.search(str(key)):
                out[key] = "***"
            else:
                out[key] = redact(value)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, tuple):
        return [redact(v) for v in obj]
    return obj


def _walk_strings(obj, path: str = "$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _walk_strings(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from _walk_strings(value, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def scan_injection(obj) -> list[dict]:
    """Tandai pola instruksi pada teks di dalam data (TEMUAN, bukan eksekusi).

    Return list {path, rule, snippet}; snippet dipotong 80 karakter.
    Maks 20 temuan agar output tetap terkendali.
    """
    findings: list[dict] = []
    for path, text in _walk_strings(obj):
        for rule in _INSTRUCTION_RE:
            match = rule.search(text)
            if match:
                findings.append({
                    "path": path,
                    "rule": rule.pattern,
                    "snippet": text[:_SNIPPET_LEN],
                })
                if len(findings) >= _MAX_FINDINGS:
                    return findings
                break
    return findings


def find_exec_injection(obj) -> list[dict]:
    """Cari pola EKSEKUSI di input argumen tool (ditolak, bukan disimpan)."""
    hits: list[dict] = []
    for path, text in _walk_strings(obj):
        for rule in _EXEC_RE:
            if rule.search(text):
                hits.append({"path": path, "rule": rule.pattern,
                             "snippet": text[:_SNIPPET_LEN]})
                if len(hits) >= _MAX_FINDINGS:
                    return hits
                break
    return hits
