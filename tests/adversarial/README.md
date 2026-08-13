# tests/adversarial

The adversarial test suite (`docs/INTERPOSE_SCOPING.md` Section 10.5, gate G9): at
least 6 documented attack classes, each with reproducible scripted MCP call
sequences and a labeled expected outcome, run in CI as a claim that Interpose
actually defends against that threat.

**Phase 4 status: real, live-verified, for all 6 classes.** Every scenario runs a
real MCP client through a real gateway subprocess talking to a real upstream server,
and the assertion is against the real audit trail (or, for two classes, the real MCP
response content or the real `incidents` table) -- never gateway internals. See
`docs/project/SESSION_LOG.md` for the two real design corrections this took to get
right: an allowlist policy unconditionally bypasses every other request-side effect
for the same server, and a response-side custom policy can never deny an
already-completed call.

## The 6 required attack classes

| Attack class | Defense mechanism | Isolated policy pack |
|---|---|---|
| `prompt_injection_via_tool_output` | Response-side custom policy detects and tags -- does not block delivery (see `interpose.policies.packs.demo`'s docstring for why) | `fixtures/policies/prompt_injection_via_tool_output/` |
| `data_exfiltration` | `rate_limit` denies the call past its window | `fixtures/policies/data_exfiltration/` |
| `unauthorized_write` | `hitl_gate` holds the call; nobody approves it, so it times out and denies | `fixtures/policies/unauthorized_write/` |
| `over_permissioned_tool_access` | `allowlist` default-denies anything not explicitly listed | `fixtures/policies/over_permissioned_tool_access/` |
| `credential_leakage` | `pii_redaction` redacts the response before it reaches the agent | `fixtures/policies/credential_leakage/` |
| `chained_tool_privilege_escalation` | Agent A4 promotes repeated denials to an incident (the direct DENY->A4 graph path, independent of Agent A2) | `fixtures/policies/chained_tool_privilege_escalation/` |

(See `attack_classes.py`'s `ATTACK_CLASS_REGISTRY` for the same information as code.)

## Why 6 separate, isolated policy directories -- not one shared pack

An `allowlist` policy for a server is an unconditional early return in
`PolicySet.evaluate` (`allowlist -> denylist -> rate_limit -> custom -> hitl_gate`):
if a tool is on the allowlist, none of the other effect types are ever even checked
for it. Discovered live, building this suite: putting `over_permissioned_tool_access`'s
allowlist policy in the same pack as `unauthorized_write`'s `hitl_gate`
policy silently made the HITL test's tool bypass its own hold entirely the moment
both existed together. Giving each attack class its own `policy_dir`
(`tests/adversarial/harness.py::scenario_gateway` starts a fresh gateway subprocess
per class, `POLICY_DIR` pointed at that one class's directory) makes this class of
bug structurally impossible -- one class's policies can never affect another's,
regardless of what either pack's YAML contains.

## What a scenario looks like

A `schema.AdversarialScenario`: an `id`, an `attack_class`, a human `description`, a
list of scripted `tools/call` steps (`server`/`tool`/`args`), and an
`ExpectedOutcome` -- the audit `status` and `policy_fired` (the two fields every
class needs), plus a few optional fields a couple of classes need beyond what the
audit trail alone can express: `response_contains`/`response_not_contains` (real MCP
response content, for `credential_leakage`'s redaction proof), `tags_include` (for
`prompt_injection_via_tool_output`'s detect-only tag), and `incident_expected` (for
`chained_tool_privilege_escalation`'s real `incidents` table row, Phase 3's
control-plane persistence work). `generate.write_fixtures`/`load_fixtures`
round-trip a list of these through JSONL in `fixtures/*.jsonl`.

## Fixture volume: a deliberate, smaller number than Section 10.5's literal ~500-1000

That number is templated-argument-permutation volume (different agent_id/session_id/
argument content against the same underlying scenario shape), not 500 meaningfully
different attacks -- the marginal signal of variant #500 over variant #5 is close to
zero, while the CI cost of a real live gateway round trip per variant is not. Each
class gets 2-4 real variants instead (`generate.py`), seeded for reproducibility,
varying a genuine axis where one exists (which PII pattern; how many repeated
denials) rather than padded to hit a bigger count.

## Running it

```sh
uv run pytest tests/adversarial/test_live_scenarios.py -v
```

Every one of the 6 parametrized cases spins up its own real gateway + hello-echo
upstream subprocess pair, runs every generated scenario for that class through it,
and tears both down -- ~20-25s total for all 6 classes on this laptop. Wired into CI
(`.github/workflows/ci.yml`) alongside the rest of the integration suite.
