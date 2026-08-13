"""Runs a real `AdversarialScenario` through a real, live gateway + upstream MCP
server pair, and checks the result against what the scenario expects to have
happened -- never against gateway internals, only the audit trail (and, for a couple
of classes, the real MCP response or the control-plane's persisted tables) a real
attacker's traffic would actually leave behind.

One gateway subprocess *per attack class*, not one shared across all six: an
allowlist policy unconditionally bypasses hitl_gate/rate_limit/denylist for every
other tool on the same server (found live, building this) -- keeping each class's
scenarios on their own isolated `policy_dir`
(`tests/adversarial/fixtures/policies/<attack_class>/`) means declaring an allowlist
for one class can never affect any other class's own policies, full stop, regardless
of what each pack's YAML happens to contain.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from sqlalchemy import create_engine, select

from interpose.audit.models import AuditEntry
from interpose.config import get_settings
from interpose.control_plane.models import IncidentRecord

from .attack_classes import AttackClass
from .schema import AdversarialScenario

REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_SCRIPT = REPO_ROOT / "examples" / "hello-mcp-http-echo" / "server.py"
POLICIES_ROOT = Path(__file__).parent / "fixtures" / "policies"

GATEWAY_URL = "http://127.0.0.1:8000"
UPSTREAM_PORT = 9001
GATEWAY_PORT = 8000

# Bounded, not indefinite -- a control-plane bug that never persists an incident
# should make this test fail loudly (AssertionError, "no incident appeared"), not
# hang the suite forever. 10s is generous for an in-process asyncio.Task that's
# already consuming from the EventBus with nothing else competing for it.
INCIDENT_POLL_TIMEOUT_SECONDS = 10.0
INCIDENT_POLL_INTERVAL_SECONDS = 0.25


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"nothing listening on {host}:{port} after {timeout}s")


@asynccontextmanager
async def scenario_gateway(attack_class: AttackClass) -> AsyncIterator[str]:
    """Starts a real hello-echo upstream + a real gateway subprocess, the gateway's
    `POLICY_DIR` pointed at exactly this attack class's isolated policy pack. Yields
    the gateway's base URL; tears both processes down on exit, same
    terminate-then-kill-on-timeout pattern as `tests/integration/conftest.py`.
    """
    policy_dir = POLICIES_ROOT / attack_class.value
    if not policy_dir.is_dir():
        raise FileNotFoundError(
            f"no isolated policy pack for {attack_class.value!r} at {policy_dir}"
        )

    upstream = subprocess.Popen([sys.executable, str(UPSTREAM_SCRIPT)])
    gateway = subprocess.Popen(
        [sys.executable, "-m", "interpose.gateway"],
        cwd=REPO_ROOT,
        env={**os.environ, "POLICY_DIR": str(policy_dir)},
    )
    try:
        _wait_for_port("127.0.0.1", UPSTREAM_PORT)
        _wait_for_port("127.0.0.1", GATEWAY_PORT)
        yield GATEWAY_URL
    finally:
        for proc in (gateway, upstream):
            proc.terminate()
        for proc in (gateway, upstream):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


@dataclass
class ScenarioResult:
    """What actually happened when a scenario's scripted calls ran for real."""

    agent_id: str
    audit_entries: list[dict[str, Any]] = field(default_factory=list)
    # One entry per scripted call: the response text if it succeeded, or the
    # McpError's structured `error.data` if the gateway rejected/failed it.
    call_outcomes: list[dict[str, Any]] = field(default_factory=list)
    incident_found: bool = False


async def run_scenario(scenario: AdversarialScenario, gateway_base_url: str) -> ScenarioResult:
    """Drives every scripted call in `scenario.calls`, in order, through one real
    MCP session (matching `test_rate_limited_tool_denies_the_second_call`'s own
    precedent for a multi-call scenario) -- then reads back what a real compliance
    query would see: the audit trail for this run's `agent_id`, and, if the scenario
    expects one, a matching `incidents` row.

    A fresh, unique `agent_id` per call to this function (not per scenario object)
    is what makes concurrent/repeated runs safe without any table truncation between
    them -- every scenario run's audit trail is self-contained and unambiguous by
    construction, the same reasoning `InvestigationClient` already uses this pattern
    for (`agents/aml-investigator/src/aml_investigator/gateway_client.py`).
    """
    agent_id = f"adversarial-{scenario.id}-{uuid.uuid4()}"
    result = ScenarioResult(agent_id=agent_id)

    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {agent_id}"}) as http_client:
        for step in scenario.calls:
            url = f"{gateway_base_url}/mcp/{step.server}"
            async with streamable_http_client(url, http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    try:
                        call_result = await session.call_tool(step.tool, step.args)
                        text_content = "".join(
                            block.text for block in call_result.content if hasattr(block, "text")
                        )
                        result.call_outcomes.append({"ok": True, "text": text_content})
                    except McpError as exc:
                        result.call_outcomes.append(
                            {"ok": False, "message": exc.error.message, "data": exc.error.data}
                        )

    result.audit_entries = _fetch_audit_entries(agent_id)

    if scenario.expected.incident_expected:
        result.incident_found = await _poll_for_incident(agent_id)

    return result


def _fetch_audit_entries(agent_id: str) -> list[dict[str, Any]]:
    engine = create_engine(get_settings().database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(AuditEntry)
                .where(AuditEntry.agent_id == agent_id)
                .order_by(AuditEntry.id)
            ).all()
            columns = [c.name for c in AuditEntry.__table__.columns]
            return [dict(zip(columns, row, strict=True)) for row in rows]
    finally:
        engine.dispose()


async def _poll_for_incident(agent_id: str) -> bool:
    """The control plane processes `DecisionEvent`s asynchronously, off the
    gateway's hot path (`interpose.control_plane.runner.run_forever`) -- by the time
    the scripted calls above have all returned, Agent A4's incident promotion (if
    any) may not have landed in Postgres yet. Polls rather than assuming either
    "already there" or a fixed sleep, matching how this project's own live
    verifications of the control-plane persistence work treated the same
    eventual-consistency gap."""
    engine = create_engine(get_settings().database_url)
    deadline = time.monotonic() + INCIDENT_POLL_TIMEOUT_SECONDS
    try:
        while time.monotonic() < deadline:
            with engine.connect() as conn:
                found = conn.execute(
                    select(IncidentRecord.id).where(IncidentRecord.agent_id == agent_id).limit(1)
                ).first()
            if found is not None:
                return True
            await asyncio.sleep(INCIDENT_POLL_INTERVAL_SECONDS)
        return False
    finally:
        engine.dispose()


def assert_scenario_result(scenario: AdversarialScenario, result: ScenarioResult) -> None:
    """The actual pass/fail judgment, kept separate from `run_scenario` so the eval
    harness (Section 4.6/14.8's "evaluation report JSON") can reuse the exact same
    live-run logic and catch this as a normal exception per scenario, rather than
    letting one failure abort the whole report."""
    if not result.audit_entries:
        raise AssertionError(
            f"{scenario.id}: no audit entries were produced for agent_id={result.agent_id!r}"
        )
    last = result.audit_entries[-1]
    expected = scenario.expected

    if last["status"] != expected.status:
        raise AssertionError(
            f"{scenario.id}: expected final status {expected.status!r}, got {last['status']!r} "
            f"(full trail: {[e['status'] for e in result.audit_entries]})"
        )
    actual_fired = last["decision"].get("fired_policy")
    if actual_fired != expected.policy_fired:
        raise AssertionError(
            f"{scenario.id}: expected fired_policy {expected.policy_fired!r}, got {actual_fired!r}"
        )
    missing_tags = [tag for tag in expected.tags_include if tag not in last["tags"]]
    if missing_tags:
        raise AssertionError(
            f"{scenario.id}: expected tags {expected.tags_include} on the final audit "
            f"entry, missing {missing_tags} (actual tags: {last['tags']})"
        )

    if result.call_outcomes and result.call_outcomes[-1].get("ok"):
        last_response_text = result.call_outcomes[-1]["text"]
        if expected.response_contains is not None and expected.response_contains not in (
            last_response_text
        ):
            raise AssertionError(
                f"{scenario.id}: expected the final response to contain "
                f"{expected.response_contains!r}, got {last_response_text!r}"
            )
        if (
            expected.response_not_contains is not None
            and expected.response_not_contains in last_response_text
        ):
            raise AssertionError(
                f"{scenario.id}: expected the final response to NOT contain "
                f"{expected.response_not_contains!r}, but it did: {last_response_text!r}"
            )

    if expected.incident_expected and not result.incident_found:
        raise AssertionError(
            f"{scenario.id}: expected an incident to be promoted for "
            f"agent_id={result.agent_id!r}, but none appeared within "
            f"{INCIDENT_POLL_TIMEOUT_SECONDS}s"
        )
