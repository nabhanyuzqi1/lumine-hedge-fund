# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for MT5 bridge command/result contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lumine.bridge.types import BridgeCommand, BridgeResult, BridgeStatus


class TestBridgeStatus:
    def test_status_values(self) -> None:
        assert {s.value for s in BridgeStatus} == {
            "pending",
            "sent",
            "acknowledged",
            "filled",
            "partial",
            "rejected",
            "error",
            "timeout",
        }


class TestBridgeCommand:
    def test_minimal_command_serializes(self) -> None:
        cmd = BridgeCommand(
            command_id="cmd-1",
            action="BUY",
            symbol="XAUUSD",
        )
        data = cmd.model_dump(mode="json")
        assert data["command_id"] == "cmd-1"
        assert data["action"] == "BUY"
        assert data["symbol"] == "XAUUSD"
        assert data["order_type"] == "market"

    def test_action_must_be_uppercase(self) -> None:
        with pytest.raises(ValueError, match="action"):
            BridgeCommand(command_id="cmd-1", action="buy", symbol="XAUUSD")

    def test_command_id_required(self) -> None:
        with pytest.raises(ValueError, match="command_id"):
            BridgeCommand(command_id="", action="BUY", symbol="XAUUSD")

    def test_symbol_required(self) -> None:
        with pytest.raises(ValueError, match="symbol"):
            BridgeCommand(command_id="cmd-1", action="BUY", symbol="")

    def test_volume_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="volume"):
            BridgeCommand(
                command_id="cmd-1",
                action="BUY",
                symbol="XAUUSD",
                volume=0.0,
            )

    def test_stop_loss_below_take_profit_for_buy(self) -> None:
        with pytest.raises(ValueError, match="stop_loss"):
            BridgeCommand(
                command_id="cmd-1",
                action="BUY",
                symbol="XAUUSD",
                stop_loss=3000.0,
                take_profit=2500.0,
            )

    def test_sell_allows_stop_loss_above_take_profit(self) -> None:
        cmd = BridgeCommand(
            command_id="cmd-1",
            action="SELL",
            symbol="XAUUSD",
            stop_loss=3000.0,
            take_profit=2500.0,
        )
        assert cmd.stop_loss == 3000.0
        assert cmd.take_profit == 2500.0

    def test_timestamp_defaults_to_utc_now(self) -> None:
        before = datetime.now(UTC)
        cmd = BridgeCommand(command_id="cmd-1", action="BUY", symbol="XAUUSD")
        after = datetime.now(UTC)
        assert before <= cmd.timestamp <= after

    def test_idempotency_key_defaults_to_command_id(self) -> None:
        cmd = BridgeCommand(command_id="cmd-1", action="BUY", symbol="XAUUSD")
        assert cmd.idempotency_key == "cmd-1"

    def test_idempotency_key_explicit_value_is_kept(self) -> None:
        # The default (bridge/types.py:69-70) only applies when no key was
        # supplied — an explicit key must survive the validator untouched.
        cmd = BridgeCommand(
            command_id="cmd-1",
            action="BUY",
            symbol="XAUUSD",
            idempotency_key="replay-key-9",
        )
        assert cmd.idempotency_key == "replay-key-9"

    def test_close_command_allows_zero_volume(self) -> None:
        # The volume > 0 check (bridge/types.py:50-52) applies only to
        # BUY/SELL — CLOSE needs no volume, so 0.0 must be legal.
        cmd = BridgeCommand(command_id="cmd-1", action="CLOSE", symbol="XAUUSD", volume=0.0)
        assert cmd.volume == 0.0

    def test_sell_rejects_stop_loss_below_take_profit(self) -> None:
        with pytest.raises(ValueError, match="stop_loss"):
            BridgeCommand(
                command_id="cmd-1",
                action="SELL",
                symbol="XAUUSD",
                stop_loss=2500.0,
                take_profit=3000.0,
            )

    def test_order_type_must_be_market_limit_stop(self) -> None:
        with pytest.raises(ValueError, match="order_type"):
            BridgeCommand(
                command_id="cmd-1",
                action="BUY",
                symbol="XAUUSD",
                order_type="stop_limit",
            )

    def test_unknown_action_rejected(self) -> None:
        with pytest.raises(ValueError, match="action"):
            BridgeCommand(command_id="cmd-1", action="HEDGE", symbol="XAUUSD")


class TestBridgeResult:
    def test_minimal_result_serializes(self) -> None:
        result = BridgeResult(
            command_id="cmd-1",
            status=BridgeStatus.FILLED,
        )
        data = result.model_dump(mode="json")
        assert data["command_id"] == "cmd-1"
        assert data["status"] == "filled"

    def test_result_with_ticket_and_fill(self) -> None:
        result = BridgeResult(
            command_id="cmd-1",
            status=BridgeStatus.FILLED,
            order_id="ord-1",
            ticket=12345,
            fill_price=2500.5,
            fill_volume=0.1,
        )
        assert result.ticket == 12345
        assert result.fill_price == 2500.5

    def test_error_result_requires_message(self) -> None:
        with pytest.raises(ValueError, match="error_message"):
            BridgeResult(
                command_id="cmd-1",
                status=BridgeStatus.ERROR,
            )

    def test_rejected_result_requires_message(self) -> None:
        with pytest.raises(ValueError, match="error_message"):
            BridgeResult(
                command_id="cmd-1",
                status=BridgeStatus.REJECTED,
            )

    def test_result_timestamp_defaults_to_utc_now(self) -> None:
        before = datetime.now(UTC)
        result = BridgeResult(
            command_id="cmd-1",
            status=BridgeStatus.FILLED,
        )
        after = datetime.now(UTC)
        assert before <= result.timestamp <= after

    def test_command_id_required(self) -> None:
        with pytest.raises(ValueError, match="command_id"):
            BridgeResult(command_id="", status=BridgeStatus.FILLED)

    def test_timeout_result_allows_no_error_message(self) -> None:
        # The required-error_message invariant (bridge/types.py:89)
        # covers only REJECTED/ERROR — TIMEOUT is an EA-side liveness
        # signal, not a rejection, and must stay constructible bare.
        result = BridgeResult(command_id="cmd-1", status=BridgeStatus.TIMEOUT)
        assert result.status is BridgeStatus.TIMEOUT
        assert result.error_message is None

    def test_partial_result_with_fill_data(self) -> None:
        result = BridgeResult(
            command_id="cmd-1",
            status=BridgeStatus.PARTIAL,
            ticket=99,
            fill_price=2501.25,
            fill_volume=0.05,
            error_code=0,
        )
        assert result.fill_volume == 0.05
        assert result.error_code == 0
