"""The audit log's hash chain (docs/INTERPOSE_SCOPING.md Section 6.7).

`this_hash = SHA-256(prev_hash || canonical_json(entry_without_this_hash))`. Each
entry's `this_hash` becomes the next entry's `prev_hash`, so mutating any historical
entry's content changes its `this_hash`, which no longer matches what the next entry
recorded as `prev_hash` -- and every entry after that is now unverifiable too. That's
what makes tampering detectable rather than just "different."

Deliberately excluded from the hashed payload: the database `id` (an auto-incrementing
storage detail, not semantic content -- the chain's order comes from prev_hash/
this_hash pointers, not from `id`). Deliberately included, per the formula above even
though it's slightly redundant: `prev_hash` itself is both the literal prefix *and* a
field inside the payload being hashed (it's a real column on the entry) -- harmless,
and matches the spec as written rather than a reinterpretation of it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# SHA-256 hex digest length, all zeros -- the well-known value the first entry in a
# chain points to as its "previous" hash, since there is no real previous entry.
GENESIS_HASH = "0" * 64

# Columns that exist on a stored row but aren't semantic content of the entry itself.
_EXCLUDED_FROM_HASH = {"id", "this_hash"}


def _json_default(obj: Any) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"not JSON-serializable for hashing: {type(obj)!r}")


def canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace, so the same
    logical entry always hashes to the same bytes regardless of dict ordering."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)


def hashable_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """The subset of an entry's fields that go into its hash -- everything except
    the fields listed in `_EXCLUDED_FROM_HASH`."""
    return {k: v for k, v in entry.items() if k not in _EXCLUDED_FROM_HASH}


def compute_entry_hash(prev_hash: str, entry: dict[str, Any]) -> str:
    payload = hashable_payload(entry)
    digest_input = prev_hash + canonical_json(payload)
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainVerificationResult:
    valid: bool
    checked: int
    first_mismatch_id: int | None = None
    detail: str | None = None


def verify_chain(entries: Sequence[dict[str, Any]]) -> ChainVerificationResult:
    """Walk `entries` (already ordered by `id` ascending) and recompute each
    `this_hash` from scratch, comparing against what's stored. Returns the first
    mismatch, if any -- verification cost is linear in row count (Section 6.7)."""
    expected_prev = GENESIS_HASH
    for i, entry in enumerate(entries):
        if entry["prev_hash"] != expected_prev:
            return ChainVerificationResult(
                valid=False,
                checked=i,
                first_mismatch_id=entry["id"],
                detail=(
                    f"entry {entry['id']} has prev_hash={entry['prev_hash']!r}, "
                    f"expected {expected_prev!r} (the prior entry's this_hash)"
                ),
            )
        recomputed = compute_entry_hash(expected_prev, entry)
        if recomputed != entry["this_hash"]:
            return ChainVerificationResult(
                valid=False,
                checked=i,
                first_mismatch_id=entry["id"],
                detail=(
                    f"entry {entry['id']} this_hash={entry['this_hash']!r} does not "
                    f"match recomputed {recomputed!r} -- content was modified after writing"
                ),
            )
        expected_prev = entry["this_hash"]

    return ChainVerificationResult(valid=True, checked=len(entries))
