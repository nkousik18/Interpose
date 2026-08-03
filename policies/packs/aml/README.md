# AML/BSA policy pack

The flagship policy pack (`docs/INTERPOSE_SCOPING.md` Section 9.8, Phase 3 Day 14).
Six active policies plus one deliberately-inactive schema stub, governing the
`ofac-sanctions` and `transaction-graph` MCP servers the AML investigation agent
(`agents/aml-investigator/`) calls through the gateway.

| Policy | Effect | Stage | What it does |
|---|---|---|---|
| `aml-sanctions-required` | `custom` (`aml_sanctions_required`) | request | Denies any transaction-graph call unless this session already has a completed OFAC sanctions check. |
| `aml-write-hitl-gate` | `hitl_gate` | request | Every `mark_investigated` call requires `aml-analysts` approval, 1-hour timeout. |
| `aml-pii-redaction` | `pii_redaction` | response | Redacts SSN/credit-card/bank-account patterns from every tool response in the pack. |
| `aml-rate-limit-sanctions` | `rate_limit` | request | Caps `check_entity` at 60 calls/minute per agent. |
| `aml-structuring-alert` | `custom` (`aml_structuring_alert`) | response | Tags the audit entry as a high-severity incident when `structuring_check` returns `flagged=true`. |
| `aml-audit-tagging` | `tag_only` | n/a | Tags every AML-pack-governed audit entry `pack:aml`, `regulation:BSA`. |

## Deviations from Section 9.8's literal wording

Named here, not silently absorbed -- each one is also documented at the point in the
code it affects.

- **P1 (`aml-sanctions-required`) is session-level, not per-account.** The doc asks
  for "a prior sanctions check *on that account*." `check_entity`/`check_alias` take
  a free-text `name`; `transaction-graph`'s tools take an `account_id`. There's no
  shared key between the two servers' actual schemas to verify "the account being
  queried is the same one that was sanctions-checked" -- so this policy checks "some
  sanctions check happened first in this session," an honest, implementable reading
  rather than a false promise of per-account traceability the tools can't back up.
- **P4 (`aml-rate-limit-sanctions`) only enforces the 60/minute threshold, not the
  doc's additional 500/hour one.** `RateLimitEffect` carries one `(limit,
  window_seconds)` pair; extending it to hold multiple thresholds is a bigger schema
  change with a wider blast radius (every existing rate-limit test, every other
  pack) for one policy's second number. Multiple `rate_limit` policies on the same
  `{server, tool}` already compose as AND, so an hourly cap could be added as a
  second file later with zero engine changes.
- **P5 (`aml-structuring-alert`) triggers on `flagged=true`, not "signal_strength >
  0.7."** No `signal_strength` field exists on the real `StructuringSignal` response
  (`mcp-servers/transaction-graph/src/graph_models.py`) -- the server only ever
  returns a boolean. Also: the doc's "requires the next mutating action in the
  session to go through HITL regardless of other policies" is real state (a Redis
  flag genuinely gets set,
  `interpose.policies.packs.aml.aml_structuring_alert`) but provably a no-op in
  *this* pack specifically, since `aml-write-hitl-gate` already HITL-gates every
  write on `transaction-graph` unconditionally -- there's no weaker state for it to
  override. The flag is still set for real, available to a reviewer or a future,
  narrower write policy.
- **P7 (`aml-cost-cap`) is not an active policy in this pack at all.** It exists as
  a schema stub (`interpose.policies.schema.CostCapEffect`) that parses and
  validates, but `PolicySet.evaluate` raises `NotImplementedError` the moment one is
  present in an applicable `PolicySet` -- there's no partial enforcement to fall
  back to, because the gateway has zero visibility into LLM token cost (an agent's
  LLM calls, like the investigation agent's Assessment/Report nodes, happen
  out-of-process, never through Interpose). Since this pack's other policies use
  `server: "*"` on purpose (`aml-pii-redaction`, `aml-audit-tagging`), activating a
  `cost_cap` policy here would make *every* AML-pack-governed call raise, not a
  useful subset -- the whole pack would stop working. Left as a demonstrated,
  tested capability (`tests/unit/policies/test_policyset.py::TestCostCapStub`)
  rather than something that breaks the pack it's supposed to belong to.

See `concepts/31-response-side-policy-evaluation-and-custom-policies.md` for the
engine-level reasoning behind response-side evaluation and the custom-policy plugin
design.
