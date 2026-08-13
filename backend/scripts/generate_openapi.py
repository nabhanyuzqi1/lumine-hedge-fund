# Copyright (c) 2026 Lumine. All rights reserved.
"""Generate the public OpenAPI contract as docs/09-api/openapi.yaml.

Idempotent by design: the CI gate (ci.yml, ``openapi-diff`` job) runs
``make openapi`` and fails on any diff, so the checked-in artifact is
always regenerated in the same PR as the API change.

Run:  python -m scripts.generate_openapi   (or ``make openapi``)
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lumine.api.app import create_app

DOCS_PATH = Path(__file__).resolve().parents[2] / "docs" / "09-api" / "openapi.yaml"


def generate() -> str:
    """Return the canonical OpenAPI 3.1 YAML document for the Lumine API."""
    app = create_app()
    schema = app.openapi()
    dumped = yaml.safe_dump(schema, sort_keys=False, allow_unicode=True)
    return str(dumped)


def main() -> None:
    # write_bytes avoids newline translation (Path.write_text converts
    # LF to CRLF on Windows, breaking the byte-identical contract test).
    DOCS_PATH.write_bytes(generate().encode("utf-8"))
    print(f"OpenAPI contract written to {DOCS_PATH}")  # noqa: T201 — CLI output


if __name__ == "__main__":
    main()
