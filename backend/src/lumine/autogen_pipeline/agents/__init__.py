# Copyright (c) 2026 Lumine. All rights reserved.

"""AutoGen agents — one importable symbol per agent role (D4-2).

Each role is a thin wrapper over the shared single-turn runner in
``agents/_base.py``. The four analysts here operate in parallel and in
isolated conversations; the IC Forum, CIO, and debate stages live in the
``autogen_pipeline`` package root (``ic_forum.py``, ``cio_proposer.py``,
``debate.py``).
"""

from __future__ import annotations

from lumine.autogen_pipeline.agents.macro_analyst import run_macro_analyst
from lumine.autogen_pipeline.agents.news_analyst import run_news_analyst
from lumine.autogen_pipeline.agents.smc_analyst import run_smc_analyst
from lumine.autogen_pipeline.agents.technical_analyst import run_technical_analyst

__all__ = (
    "run_macro_analyst",
    "run_news_analyst",
    "run_smc_analyst",
    "run_technical_analyst",
)
