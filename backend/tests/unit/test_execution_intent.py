"""Unit tests for execution intent + MT5 bridge semantic commands (19 Aug 2026 P0)."""

import uuid

from lumine.trading.execution_intent import (
    INTENT_TO_ACTION,
    ExecutionIntent,
    primitive_action,
)
from lumine.trading.mt5_bridge import (
    create_close_order_command,
    create_modify_command,
    create_open_order_command,
)


def test_intent_to_action_mapping():
    assert primitive_action(ExecutionIntent.OPEN_POSITION) == "OPEN"
    assert primitive_action(ExecutionIntent.CLOSE_POSITION) == "CLOSE"
    assert primitive_action(ExecutionIntent.PARTIAL_CLOSE) == "CLOSE"
    assert primitive_action(ExecutionIntent.CUT_LOSS) == "CLOSE"
    assert primitive_action(ExecutionIntent.BREAKEVEN) == "MODIFY"
    assert primitive_action(ExecutionIntent.TRAILING_STOP) == "MODIFY"
    assert primitive_action(ExecutionIntent.MODIFY_STOP_LOSS) == "MODIFY"
    assert primitive_action(ExecutionIntent.MODIFY_TAKE_PROFIT) == "MODIFY"


def test_all_intents_have_primitive_action():
    for intent in ExecutionIntent:
        assert intent in INTENT_TO_ACTION


def test_open_command_carries_intent():
    oid = uuid.uuid4()
    msg = create_open_order_command(oid, "XAUUSD", 0.01, "BUY", stop_loss=4300.0, take_profit=4400.0)
    assert msg.action == "OPEN"
    assert msg.intent == "OPEN_POSITION"
    assert msg.stop_loss == 4300.0
    p = msg.as_payload()
    assert p["sl"] == 4300.0
    assert p["tp"] == 4400.0


def test_close_command_now_carries_ticket():
    """Regression: create_close_order_command SEBELUMNYA drop ticket → EA gagal."""
    oid = uuid.uuid4()
    msg = create_close_order_command(oid, 259014664, reason="manual")
    assert msg.ticket == 259014664
    assert msg.intent == "CLOSE_POSITION"
    assert msg.as_payload()["ticket"] == 259014664


def test_modify_command_intent_distinguishes_be_trailing():
    oid = uuid.uuid4()
    be = create_modify_command(oid, 123, stop_loss=4350.0, intent="BREAKEVEN", reason="BE hit")
    trail = create_modify_command(oid, 123, stop_loss=4360.0, intent="TRAILING_STOP", reason="trail")
    assert be.intent == "BREAKEVEN"
    assert trail.intent == "TRAILING_STOP"
    assert be.action == trail.action == "MODIFY"
    assert be.as_payload()["intent"] == "BREAKEVEN"
