# Copyright (c) 2026 Lumine. All rights reserved.
"""Contract test for the generated OpenAPI document (docs/09-api/openapi.yaml).

Validates the checked-in public contract against api-versioning.md:
versioned paths, router coverage, HMAC header parameters, and the
envelope-shaped error response schema.
"""

from __future__ import annotations

from pathlib import Path

import yaml

OPENAPI_PATH = Path(__file__).resolve().parents[3] / "docs" / "09-api" / "openapi.yaml"

# Every domain router mounted in app.create_app under the /api/v1 prefix
# (src/lumine/api/app.py:75-86).
EXPECTED_ROUTER_TAGS = {
    "portfolio",
    "orders",
    "workflows",
    "lineage",
    "market",
    "journal",
    "streams",
    "admin",
    "rpc",
}

HMAC_HEADERS = {"X-Lumine-API-Key", "X-Lumine-Timestamp", "X-Lumine-Signature"}


def _load_schema() -> dict[str, object]:
    """Load the checked-in OpenAPI document as a dict."""
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


def test_openapi_is_versioned_31() -> None:
    schema = _load_schema()
    assert schema["openapi"] == "3.1.0"
    assert schema["info"]["title"] == "Lumine API"
    assert schema["info"]["version"] == "0.1.0"


def test_all_paths_live_under_api_v1_prefix() -> None:
    schema = _load_schema()
    paths = [path for path in schema["paths"] if path != "/health"]
    assert paths, "openapi.yaml must declare at least one path"
    # /api/auth/* (first-party session auth, no HMAC) is the documented
    # exception — login/logout/me/verify are consumed by the SPA and by
    # Caddy forward_auth, never by HMAC-signed machine clients.
    auth_paths = [p for p in paths if p.startswith("/api/auth/")]
    api_paths = [p for p in paths if not p.startswith("/api/auth/")]
    assert all(p.startswith("/api/v1/") for p in api_paths), (
        f"unversioned paths: {[p for p in api_paths if not p.startswith('/api/v1/')]}"
    )
    assert auth_paths, "auth router must be present in the schema"


def test_all_nine_routers_present() -> None:
    schema = _load_schema()
    tags: set[str] = set()
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if isinstance(operation, dict) and "tags" in operation:
                tags.update(operation["tags"])
    assert tags >= EXPECTED_ROUTER_TAGS, (
        f"missing router tags: {sorted(EXPECTED_ROUTER_TAGS - tags)}"
    )


def test_every_operation_declares_hmac_headers() -> None:
    schema = _load_schema()
    checked = 0
    for path, path_item in schema["paths"].items():
        if path == "/health":
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            # /api/auth/* uses the session cookie flow, not HMAC headers.
            if path.startswith("/api/auth/"):
                continue
            params = {p["name"] for p in operation.get("parameters", []) if p.get("in") == "header"}
            assert params >= HMAC_HEADERS, (
                f"missing HMAC headers on {operation.get('operationId', path)}: "
                f"{sorted(HMAC_HEADERS - params)}"
            )
            checked += 1
    assert checked > 0


def test_error_responses_use_envelope_shape() -> None:
    schema = _load_schema()
    # The envelope middleware converts every error into
    # {"error": {code, message, trace_id}} (error-contract.md).
    unversioned = next(p for p in schema["paths"] if p.startswith("/api/v1"))
    error_schema = schema["paths"][unversioned]["get"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]
    assert error_schema == {"$ref": "#/components/schemas/HTTPValidationError"}


def test_checked_in_contract_matches_generated_schema() -> None:
    """The YAML must be byte-identical to what app.openapi() emits today."""
    from lumine.api.app import create_app

    app = create_app()
    generated = yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True).encode()
    checked_in = OPENAPI_PATH.read_bytes()
    assert checked_in == generated, (
        "openapi.yaml is stale — regenerate with `make openapi` "
        "(or `uv run python -m scripts.generate_openapi`) and commit the diff"
    )
