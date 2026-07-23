"""Unit tests for interpose.audit.chain -- pure hash-chain logic, no database
involved. These mirror the adversarial test the scoping doc's G3 calls for: mutate an
entry, confirm verification fails.
"""

import uuid
from datetime import UTC, datetime

import pytest

from interpose.audit.chain import (
    GENESIS_HASH,
    canonical_json,
    compute_entry_hash,
    hashable_payload,
    verify_chain,
)


def _entry(**overrides: object) -> dict:
    base = {
        "id": overrides.pop("id", 1),
        "trace_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "span_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "parent_id": None,
        "timestamp": datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC),
        "status": "COMPLETED",
        "agent_id": "agent-1",
        "session_id": "session-1",
        "server": "hello-echo",
        "tool": "echo",
        "args_hash": "deadbeef",
        "args_redacted": {"text": "hi"},
        "policies_fired": [],
        "decision": {"outcome": "PASS"},
        "latency_ms": 12,
        "tokens": None,
        "prev_hash": GENESIS_HASH,
        "this_hash": "",
        "hitl_ticket_id": None,
        "hitl_reviewer": None,
        "hitl_decision": None,
        "hitl_rationale": None,
    }
    base.update(overrides)
    return base


def _chain(n: int) -> list[dict]:
    entries = []
    prev = GENESIS_HASH
    for i in range(1, n + 1):
        entry = _entry(id=i, prev_hash=prev)
        entry["this_hash"] = compute_entry_hash(prev, entry)
        entries.append(entry)
        prev = entry["this_hash"]
    return entries


class TestCanonicalJson:
    def test_deterministic_regardless_of_key_order(self) -> None:
        a = canonical_json({"a": 1, "b": 2})
        b = canonical_json({"b": 2, "a": 1})
        assert a == b

    def test_serializes_datetime_and_uuid(self) -> None:
        payload = {
            "when": datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC),
            "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        }
        result = canonical_json(payload)
        assert "2026-07-22T12:00:00+00:00" in result
        assert "11111111-1111-1111-1111-111111111111" in result

    def test_raises_on_unserializable_object(self) -> None:
        with pytest.raises(TypeError):
            canonical_json({"bad": object()})


class TestHashablePayload:
    def test_excludes_id_and_this_hash(self) -> None:
        entry = _entry(id=42, this_hash="whatever")
        payload = hashable_payload(entry)
        assert "id" not in payload
        assert "this_hash" not in payload

    def test_id_does_not_affect_the_hash(self) -> None:
        entry_a = _entry(id=1)
        entry_b = _entry(id=999)
        hash_a = compute_entry_hash(GENESIS_HASH, entry_a)
        hash_b = compute_entry_hash(GENESIS_HASH, entry_b)
        assert hash_a == hash_b

    def test_changing_a_real_field_changes_the_hash(self) -> None:
        entry_a = _entry(tool="echo")
        entry_b = _entry(tool="dangerous_tool")
        hash_a = compute_entry_hash(GENESIS_HASH, entry_a)
        hash_b = compute_entry_hash(GENESIS_HASH, entry_b)
        assert hash_a != hash_b


class TestVerifyChain:
    def test_empty_chain_is_valid(self) -> None:
        result = verify_chain([])
        assert result.valid
        assert result.checked == 0

    def test_valid_chain_of_several_entries(self) -> None:
        result = verify_chain(_chain(5))
        assert result.valid
        assert result.checked == 5

    def test_detects_broken_genesis(self) -> None:
        entries = _chain(3)
        entries[0]["prev_hash"] = "f" * 64
        result = verify_chain(entries)
        assert not result.valid
        assert result.first_mismatch_id == entries[0]["id"]

    def test_detects_mutated_field_in_a_later_entry(self) -> None:
        entries = _chain(5)
        entries[2]["tool"] = "mark_investigated"  # mutated after the fact
        result = verify_chain(entries)
        assert not result.valid
        assert result.first_mismatch_id == entries[2]["id"]

    def test_detects_broken_link_between_entries(self) -> None:
        entries = _chain(4)
        entries[2]["prev_hash"] = "e" * 64
        result = verify_chain(entries)
        assert not result.valid
        assert result.first_mismatch_id == entries[2]["id"]

    def test_verification_stops_at_first_mismatch(self) -> None:
        entries = _chain(5)
        entries[1]["tool"] = "tampered"
        result = verify_chain(entries)
        assert result.checked == 1
        assert result.first_mismatch_id == entries[1]["id"]
