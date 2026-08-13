"""Phase 4, Day 16 acceptance test (docs/ROADMAP.md; docs/INTERPOSE_SCOPING.md Section
10.5, gate G9): every generated scenario for every one of the 6 required attack
classes, run for real through a live gateway + real upstream MCP server, checked
against the real audit trail (and, for a couple of classes, the real MCP response or
the real `incidents` table) -- not against gateway internals. If this file is green,
Interpose actually defends against all 6 attack classes, demonstrated live, not
merely asserted in prose.

One gateway subprocess per attack class (not per scenario) -- `scenario_gateway` is
class-scoped, matching `tests/integration/conftest.py`'s own module-scoped upstream
fixtures; every scenario for a given class shares that one gateway/upstream pair,
safe because each `run_scenario` call gets its own unique `agent_id`
(`tests.adversarial.harness`'s own reasoning for why).
"""

import pytest

from .attack_classes import AttackClass
from .generate import generate
from .harness import assert_scenario_result, run_scenario, scenario_gateway

SCENARIOS_PER_CLASS = 4
SEED = 42


@pytest.mark.parametrize("attack_class", list(AttackClass), ids=lambda ac: ac.value)
async def test_attack_class_is_defended_against(attack_class: AttackClass) -> None:
    scenarios = generate(attack_class, count=SCENARIOS_PER_CLASS, seed=SEED)
    assert scenarios, f"generate() produced zero scenarios for {attack_class.value}"

    async with scenario_gateway(attack_class) as gateway_url:
        for scenario in scenarios:
            result = await run_scenario(scenario, gateway_url)
            assert_scenario_result(scenario, result)
