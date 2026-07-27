# tests/adversarial

The adversarial test suite (`docs/INTERPOSE_SCOPING.md` Section 10.5, gate G9): at
least 6 documented attack classes, each with reproducible scripted MCP call
sequences and a labeled expected outcome, run in CI as a claim that Interpose
actually defends against that threat.

**Phase 2 Day 10 status: skeleton only, zero real scenarios.** This directory has the
schema a scenario must satisfy (`schema.py`), the registry of the 6 required attack
classes (`attack_classes.py`), and the JSONL read/write machinery (`generate.py`) --
but `generate()` raises `NotImplementedError` for every class right now
(`test_skeleton.py` asserts this deliberately, not as a bug). See
`docs/ROADMAP.md`/`docs/project/SESSION_LOG.md` for why: writing scenario templates
ahead of a harness that runs them through a live gateway would just be untested
prose, and two classes need gateway capabilities that don't exist yet regardless.

## The 6 required attack classes

| Attack class | Defense mechanism | What's missing before a real fixture |
|---|---|---|
| `prompt_injection_via_tool_output` | Response-side (Hook 2) policy scan, quarantine for HITL | **A gateway capability**: only the pre-forward hook (Hook 1) is wired in today |
| `data_exfiltration` | `rate_limit`/denylist policy + Agent A2 anomaly detection | Just a scripted fixture -- the enforcement already exists |
| `unauthorized_write` | `hitl_gate` policy holds the call | Just a scripted fixture |
| `over_permissioned_tool_access` | allowlist policy denies at `tools/call` | Just a scripted fixture |
| `credential_leakage` | `pii_redaction` policy redacts and audits | **A gateway capability**: `pii_redaction` is still a schema-only stub (`interpose.policies.schema`) that raises `NotImplementedError` if evaluated |
| `chained_tool_privilege_escalation` | Agent A2 anomaly detector + Agent A4 incident escalator promote the pattern | Just a scripted fixture -- both agents already exist |

(See `attack_classes.py`'s `ATTACK_CLASS_REGISTRY` for the same information as code,
not just this table -- that's the one `test_skeleton.py` actually checks against.)

## What a real scenario will look like

A `schema.AdversarialScenario`: an `id`, an `attack_class`, a human `description`, a
list of scripted `tools/call` steps (`server`/`tool`/`args`), and an `ExpectedOutcome`
(the audit `status` -- `INTENT`/`COMPLETED`/`DENIED`/`HELD`/`UPSTREAM_ERROR`, per
`interpose.audit.models.STATUSES` -- plus which policy, if any, should have fired).
`generate.write_fixtures`/`load_fixtures` round-trip a list of these through JSONL in
`fixtures/`, per Section 10.5's storage format.

## Closing the gap (Phase 4)

1. Build the two missing gateway capabilities (response-side policy hook; real
   `pii_redaction`).
2. Write a harness that runs a scenario's `calls` through a real live gateway (same
   subprocess pattern as `tests/integration/conftest.py`) and asserts the resulting
   audit entries match `expected`.
3. Only then write real templates in `generate.py` and let it actually produce the
   ~500-1000 variants per class Section 10.5 calls for.
