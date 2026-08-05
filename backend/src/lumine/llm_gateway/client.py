# Copyright (c) 2026 Lumine. All rights reserved.
"""9router HTTP client (OpenAI-compatible wire contract, D3-2).

The client is deliberately thin: it maps a ``RouterRequest`` onto the
OpenAI ``/v1/chat/completions`` wire shape (Bearer auth, logical
admission-control fields), parses the response back into a
``GatewayResponse``, and classifies failures as ``RouterClientError``.
All HTTP I/O goes through an injected ``httpx.AsyncClient`` transport so
tests can substitute ``httpx.MockTransport`` without touching the
network or global state.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import httpx

from lumine.llm_gateway.types import GatewayResponse, RouterRequest

if TYPE_CHECKING:
    from collections.abc import Mapping


class RouterClientError(RuntimeError):
    """Raised for any gateway failure: HTTP status, timeout, bad payload."""


class RouterClient:
    """OpenAI-compatible client for the 9router gateway."""

    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        """Configure the client.

        ``transport`` is injected for tests (``httpx.MockTransport``);
        default ``None`` builds the real async HTTP transport.
        """
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(self._timeout_s),
        )

    def complete(self, req: RouterRequest) -> GatewayResponse:
        """Send ``req`` and parse the gateway's response.

        Blocking on purpose: the pipeline calls the gateway
        synchronously (same discipline as the bridge client), so the
        async HTTP request is driven to completion here.
        """
        return asyncio.run(self.complete_async(req))

    async def complete_async(self, req: RouterRequest) -> GatewayResponse:
        """Send ``req`` and parse the gateway's response (awaitable).

        Used by the gateway orchestrator's fallback chain, which runs
        one event loop per hop; ``complete`` is the blocking wrapper.
        """
        url = f"{self._url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": req.model,
            "messages": [m.model_dump() for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            # Logical fields for gateway admission control (9router
            # ignores unknown keys per the OpenAI spec).
            "lineage_id": str(req.lineage_id),
            "role": req.role,
            "tier": req.tier.value,
            "idempotency_key": req.idempotency_key,
            "prompt_ref": req.prompt_ref,
            "prompt_hash": req.prompt_hash,
        }
        try:
            resp = await self._client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            message = f"timed out: {exc}"
            raise RouterClientError(message) from exc
        if resp.status_code != 200:
            message = f"HTTP {resp.status_code}: {resp.text[:200]}"
            raise RouterClientError(message)
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            message = f"invalid JSON: {exc}"
            raise RouterClientError(message) from exc
        return self._parse(data)

    @staticmethod
    def _parse(data: Mapping[str, Any]) -> GatewayResponse:
        choices = data.get("choices") or []
        if not choices:
            message = "no choices in response"
            raise RouterClientError(message)
        choice_msg = choices[0].get("message") or {}
        content = choice_msg.get("content")
        if content is None:
            message = "no content in first choice"
            raise RouterClientError(message)
        usage = data.get("usage") or {}
        try:
            prompt_tokens = int(usage["prompt_tokens"])
            completion_tokens = int(usage["completion_tokens"])
            total_tokens = int(usage["total_tokens"])
        except (KeyError, TypeError, ValueError) as exc:
            message = f"usage missing or invalid: {exc}"
            raise RouterClientError(message) from exc
        return GatewayResponse(
            content=str(content),
            model_used=str(data.get("model", "")),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )


__all__ = ("RouterClient", "RouterClientError")
