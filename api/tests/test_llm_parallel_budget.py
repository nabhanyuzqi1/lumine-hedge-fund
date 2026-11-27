"""Regresi pipa multi-agent paralel: `budget` wajib sampai ke kedua layer.

Konteks: `_run_parallel_pipeline` sempat memanggil synthesizer dengan
`budget=budget` padahal parameter itu tidak ada di signature-nya. Akibatnya
setiap siklus paralel (llm_models.parallel=true) melempar NameError, gather
mengembalikan exception, dan loop mencatat `simbol X gagal: NameError`.
Tidak ada satu pun tes lama yang menyentuh glue ini, jadi kerusakan itu lolos.

Tes di bawah memanggil fungsi aslinya dengan specialist/synthesizer palsu dan
memastikan anggaran benar-benar diteruskan (atau di-resolve saat None).
"""
from __future__ import annotations

import asyncio

import pytest

from app import llm_agent_loop as loop
from app import llm_budget, llm_specialists


class _FakeResp:
    status_code = 200
    text = ""


class _FakeHttp:
    async def post(self, *args, **kwargs):  # noqa: D401 - stub
        return _FakeResp()

    async def get(self, *args, **kwargs):
        return _FakeResp()


@pytest.fixture()
def patched(monkeypatch):
    seen: dict = {"specialist_budget": None, "synth_budgets": []}

    async def fake_run_specialists(http, ctx, *, symbol, base, key, model,
                                   timeout_s=None, role_models=None,
                                   on_update=None, budget=None, **kw):
        seen["specialist_budget"] = budget
        seen["symbol"] = symbol
        return {
            role: {"state": "ok", "data": {"role": role}, "model": model, "latency_ms": 1}
            for role in llm_specialists.ROLES
        }

    async def fake_synthesize(http, ctx, evidence, *, symbol, base, key, model,
                              timeout_s=None, budget=None, **kw):
        seen["synth_budgets"].append(budget)
        return {
            "data": {"kind": "hold", "symbol": symbol, "reasoning": "tes",
                     "confidence": 0.5},
            "raw": "{}",
            "model": model,
            "latency_ms": 2,
            "prompt_tokens": 10,
            "completion_tokens": 5,
        }

    async def noop_post_evidence(*args, **kwargs):
        return None

    monkeypatch.setattr(llm_specialists, "run_specialists", fake_run_specialists)
    monkeypatch.setattr(llm_specialists, "synthesize", fake_synthesize)
    monkeypatch.setattr(loop, "_post_evidence", noop_post_evidence)
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/llm")
    monkeypatch.setenv("LLM_API_KEY", "dummy")
    return seen


def _cfg() -> dict:
    return {"specialist": "lucif-flash", "synth": "lucif",
            "fallback": "lucif-claude", "roles": {"technical": "lucif-claude"}}


def test_parallel_pipeline_passes_explicit_budget(patched):
    budget = llm_budget.resolve({"llm_budget": {"max_tokens": 321}})
    res = asyncio.run(loop._run_parallel_pipeline(
        _FakeHttp(), None, {}, _cfg(), "cyc-1", "XAUUSD", budget=budget))
    assert res["decision"]["kind"] == "hold"
    assert patched["specialist_budget"] == budget
    assert patched["synth_budgets"] == [budget]


def test_parallel_pipeline_resolves_budget_when_none(patched):
    res = asyncio.run(loop._run_parallel_pipeline(
        _FakeHttp(), None, {}, _cfg(), "cyc-2", "BTCUSD"))
    assert res["decision"]["symbol"] == "BTCUSD"
    expected = llm_budget.resolve({})
    assert patched["specialist_budget"] == expected
    assert patched["synth_budgets"] == [expected]


def test_parallel_pipeline_falls_back_to_fallback_model(patched, monkeypatch):
    calls: list[str] = []

    async def failing_synth(http, ctx, evidence, *, symbol, base, key, model,
                            timeout_s=None, budget=None, **kw):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("synth mati")
        return {"data": {"kind": "hold", "symbol": symbol, "reasoning": "-",
                         "confidence": 0.1},
                "model": model, "latency_ms": 1}

    monkeypatch.setattr(llm_specialists, "synthesize", failing_synth)
    res = asyncio.run(loop._run_parallel_pipeline(
        _FakeHttp(), None, {}, _cfg(), "cyc-3", "XAUUSD"))
    assert calls == ["lucif", "lucif-claude"]
    assert res["model"] == "lucif-claude"
