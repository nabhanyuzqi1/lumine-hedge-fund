# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the 9router HTTP client (OpenAI-compatible wire contract).

Uses ``httpx.MockTransport`` so no real network is touched. Covers the
D3-2 wire contract: request shape, Bearer auth, response parsing,
timeout/retry behavior, and error mapping. Fallback-chain behaviour is
tested separately in test_llm_routing (fallback module).
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from lumine.llm_gateway.client import RouterClient, RouterClientError
from lumine.llm_gateway.types import (
    ChatMessage,
    GatewayResponse,
    ModelTier,
    RouterRequest,
)

_GATEWAY_URL = "http://gateway.test:8080"
_API_KEY = "test-key-123"


def _make_client(
    handler: Any,
    *,
    url: str = _GATEWAY_URL,
    api_key: str = _API_KEY,
) -> RouterClient:
    transport = httpx.MockTransport(handler)
    return RouterClient(url=url, api_key=api_key, transport=transport)


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": '{"action": "HOLD"}',
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 40,
                "total_tokens": 160,
            },
            "model": "deepseek-v4",
        },
    )


def _sample_request() -> RouterRequest:
    return RouterRequest(
        model_version_id=uuid.uuid4(),
        role="technical_analyst",
        tier=ModelTier.COST_EFFICIENT,
        lineage_id=uuid.uuid4(),
        prompt_ref="technical_analyst@v1.prompt",
        prompt_hash="a" * 64,
        idempotency_key="idem-1",
        messages=[
            ChatMessage(role="system", content="You are an analyst."),
            ChatMessage(role="user", content="Symbol: XAUUSD"),
        ],
    )


class TestWireContract:
    def test_request_has_openai_shape(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["json"] = request.read().decode()
            captured["auth"] = request.headers.get("authorization")
            captured["url"] = str(request.url)
            return _ok_handler(request)

        client = _make_client(handler)
        client.complete(_sample_request())

        import json

        body = json.loads(captured["json"])
        assert body["model"] == "deepseek-v4"
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["content"] == "Symbol: XAUUSD"
        assert body["temperature"] == 0.2
        assert captured["auth"] == f"Bearer {_API_KEY}"
        assert captured["url"].endswith("/v1/chat/completions")

    def test_response_parses_usage_and_model(self) -> None:
        client = _make_client(_ok_handler)
        resp = client.complete(_sample_request())
        assert isinstance(resp, GatewayResponse)
        assert resp.content == '{"action": "HOLD"}'
        assert resp.model_used == "deepseek-v4"
        assert resp.prompt_tokens == 120
        assert resp.completion_tokens == 40
        assert resp.total_tokens == 160

    def test_trailing_slash_url_is_normalized(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return _ok_handler(request)

        transport = httpx.MockTransport(handler)
        client = RouterClient(
            url="http://gateway.test:8080///",
            api_key=_API_KEY,
            transport=transport,
        )
        client.complete(_sample_request())
        # rstrip("/") (client.py:47) must collapse the trailing slashes
        # so the wire URL stays a single /v1/chat/completions.
        assert captured["url"].endswith("/v1/chat/completions")
        assert "//v1" not in captured["url"]

    def test_request_carries_logical_fields(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["json"] = request.read().decode()
            return _ok_handler(request)

        client = _make_client(handler)
        req = _sample_request()
        client.complete(req)

        import json

        body = json.loads(captured["json"])
        # 9router ignores unknown fields per OpenAI spec — but we still
        # send the logical fields so gateway admission control can use them.
        assert body["lineage_id"] == str(req.lineage_id)
        assert body["role"] == "technical_analyst"
        assert body["tier"] == "cost-efficient"
        assert body["idempotency_key"] == "idem-1"
        assert body["prompt_ref"] == "technical_analyst@v1.prompt"
        assert body["prompt_hash"] == "a" * 64


class TestErrors:
    def test_401_raises_router_client_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        client = _make_client(handler)
        with pytest.raises(RouterClientError, match="401"):
            client.complete(_sample_request())

    def test_429_raises_rate_limit_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "rate limited"})

        client = _make_client(handler)
        with pytest.raises(RouterClientError, match="429"):
            client.complete(_sample_request())

    def test_5xx_raises_router_client_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": "upstream down"})

        client = _make_client(handler)
        with pytest.raises(RouterClientError, match="503"):
            client.complete(_sample_request())

    def test_timeout_raises_router_client_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out")

        client = _make_client(handler)
        with pytest.raises(RouterClientError, match="timed out"):
            client.complete(_sample_request())

    def test_empty_choices_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [], "usage": {}})

        client = _make_client(handler)
        with pytest.raises(RouterClientError, match="no choices"):
            client.complete(_sample_request())

    def test_missing_usage_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

        client = _make_client(handler)
        with pytest.raises(RouterClientError, match="usage"):
            client.complete(_sample_request())

    def test_partial_usage_raises(self) -> None:
        # usage dict present but a required counter missing — the
        # int(usage["total_tokens"]) KeyError path in _parse
        # (client.py:117-122) must raise RouterClientError, not crash.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "x"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            )

        client = _make_client(handler)
        with pytest.raises(RouterClientError, match="usage"):
            client.complete(_sample_request())

    def test_missing_content_raises(self) -> None:
        # Defensive path client.py:112-114: a choice with an absent
        # message.content must surface as RouterClientError.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"role": "assistant"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

        client = _make_client(handler)
        with pytest.raises(RouterClientError, match="content"):
            client.complete(_sample_request())

    def test_missing_model_defaults_to_empty_string(self) -> None:
        # client.py:125: model_used falls back to "" when the gateway
        # omits the model field — the parse must not crash.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "x"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

        client = _make_client(handler)
        resp = client.complete(_sample_request())
        assert resp.model_used == ""

    def test_non_json_body_raises_invalid_json(self) -> None:
        # client.py:99: resp.json() on a non-JSON 200 body must surface
        # as RouterClientError — never a raw JSONDecodeError.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>not json</html>")

        client = _make_client(handler)
        with pytest.raises(RouterClientError, match="invalid JSON"):
            client.complete(_sample_request())

    def test_non_numeric_usage_raises(self) -> None:
        # client.py:117-120: usage values that fail int() coercion must
        # surface as RouterClientError — same contract as missing keys.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "x"}}],
                    "usage": {
                        "prompt_tokens": "abc",
                        "completion_tokens": 5,
                        "total_tokens": 2,
                    },
                },
            )

        client = _make_client(handler)
        with pytest.raises(RouterClientError, match="usage"):
            client.complete(_sample_request())
