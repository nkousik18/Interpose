# Adversarial testing, and the eval harness it turned out to already be

Phase 4, Day 16 (`docs/ROADMAP.md`; `docs/INTERPOSE_SCOPING.md` Section 10.5, gate
G9). Closes a skeleton left over from Phase 2 Day 10 (`tests/adversarial/`) that had
the schema and attack-class registry in place but `generate()` raising
`NotImplementedError` for every class.

## What "adversarial testing" means here

Not fuzzing, not a red-team engagement, not trying to find *novel* attacks. Section
10.5 defines it narrowly and concretely: pick a fixed list of known attack *shapes* an
MCP gateway should defend against, script a realistic sequence of tool calls for each,
and assert — against the real, live system, not a mock — that the defense actually
fires. It's a claim, made testably: "Interpose defends against prompt injection via
tool output" is either backed by a green, live-verified test, or it isn't a claim this
project gets to make.

That "against the real, live system" part is the whole design constraint. A scenario
never asserts against gateway internals (a mocked `PolicySet.evaluate()` call, a
patched Redis) — it drives a real MCP client through a real gateway subprocess talking
to a real upstream server, and checks what a real compliance officer or SRE would
actually be able to see afterward: the audit trail, the real MCP response the caller
received, or (for one class) the control plane's own persisted incident record.

## A design mistake this project's own architecture predicted, then caught live

Building the `over_permissioned_tool_access` fixture, adding an `allowlist` policy to
the same policy directory the `hitl_gate`/`rate_limit` demo policies already lived in
silently broke those other two policies — not a bug exactly, but a direct, documented
consequence of how `PolicySet.evaluate` is built:
[[16-policy-engine-composition]] already explains that declaring an allowlist for a
server flips *default-deny* for every tool on it, but the sharper fact — that
`allow_hit` is checked and returned *before* denylist, rate_limit, or hitl_gate are
ever reached at all — means a tool on the allowlist bypasses every other effect type
outright, not just the ones targeting it directly. Two real, previously-passing tests
started failing the moment both policies coexisted.

The fix wasn't a code change to `PolicySet` (that behavior is correct and intentional
— see its own module docstring) — it was giving each attack class its own, fully
isolated `policy_dir`
(`tests/adversarial/fixtures/policies/<attack_class>/`), so one class's policies can
never interact with another's, structurally, regardless of what either pack's YAML
contains. `tests/adversarial/harness.py::scenario_gateway` starts a fresh gateway
subprocess per class for exactly this reason.

## A second one: response-side policies can't block, only tag

`prompt_injection_via_tool_output`'s doc'd defense is "quarantine for HITL" — but
`interpose.policies.custom`'s own module docstring already says a response-side
custom policy "can never deny a call that's already completed." The real precedent
(`aml_structuring_alert`, the AML pack's own response-side detection policy) confirms
it: it tags the audit entry and sets a Redis flag, but the tainted response still
reaches the caller every time. There is no fail-closed block at Stage 8 today, and
building one would mean reversing a documented architectural boundary — real new
scope, not a fixture.

The honest fix: `interpose.policies.packs.demo.hello_echo_prompt_injection_scan`
detects and tags, exactly like `aml_structuring_alert` does, and the scenario asserts
exactly that (a `COMPLETED` status, the detection tag present) — not that the response
was blocked. A named, accurate limitation is worth more than a test that quietly
demonstrates something the system doesn't actually do.

## What each attack class actually proves, live

| Class | What's scripted | What's checked |
|---|---|---|
| `prompt_injection_via_tool_output` | A tool response containing an injected instruction | The audit entry is tagged `prompt-injection-detected` |
| `data_exfiltration` | The same rate-limited tool called twice | The second call is denied, `rate_limit_exceeded` |
| `unauthorized_write` | A write-shaped tool, nobody reviews the resulting ticket | It times out and denies — never executes without a human decision |
| `over_permissioned_tool_access` | A tool never granted on the allowlist | Denied with no fired policy (`not_on_allowlist`) — default-deny by omission |
| `credential_leakage` | A response containing a fake SSN/credit-card/bank-account number | The real MCP response comes back redacted, the raw value absent |
| `chained_tool_privilege_escalation` | The same denied tool probed repeatedly | A real row lands in the `incidents` table (Phase 3's persistence work), via the direct DENY→Agent A4 graph path, independent of Agent A2 |

## Fixture volume: real coverage, not a padded number

Section 10.5 asks for ~500-1000 generated variants per class. That's
templated-argument-permutation volume, not 500 meaningfully different attacks — most
of it would be near-duplicate scenarios differing only in a random UUID. Each class
gets 2-4 *real* variants instead (`generate.py`), seeded with Python's `random.Random`
for reproducibility (the same "seed 42" precedent `interpose.analytics.subsample_aml`
already set), each varying a genuine axis where one actually exists (which PII pattern
gets leaked; how many times the agent probes before an incident promotes) rather than
padded to hit a number nothing downstream needs.

## The eval harness was already built — evaluation just needed reuse, not a new concept

Section 12.2 separates observability, audit, and *evaluation* as three distinct
concerns — evaluation "for builders... backed by the evaluation harness... regression
is a build failure." Section 4.6/14.8 both reference an eval harness and an
"evaluation report JSON" release deliverable, but `docs/ROADMAP.md` never actually
scheduled building one anywhere across Phases 0-4 — a real gap between what the
release checklist implied and what the plan ever scoped.

Closing it needed no new machinery: `tests/adversarial/harness.py`'s `run_scenario` +
`assert_scenario_result` *is* an evaluation harness already — "run a scripted scenario
against the real system, check a pass/fail outcome" is the mechanism Section 12.2
describes, built for a different immediate purpose (a live security claim, checked in
CI) but structurally identical to what regression-detection evaluation needs.
`scripts/run_eval_report.py` reuses it directly: same scenarios, same harness, pointed
at producing a JSON summary (pass/fail per scenario, aggregate counts) instead of
raising a pytest failure. CI uploads it as a build artifact on every push
(`.github/workflows/ci.yml`'s `adversarial` job) — the same file Day 20's release
process attaches to the v0.1.0 tag, not a separate one generated specially for that
moment.
