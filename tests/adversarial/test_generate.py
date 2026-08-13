"""Tests for the fixture generator itself (Phase 4) -- pure Pydantic/generation
logic, no live gateway needed. Real per-attack-class *live* proof (each generated
scenario actually run through a real gateway) is `test_live_scenarios.py`, not here.
"""

import pytest

from .attack_classes import ATTACK_CLASS_REGISTRY, AttackClass
from .generate import generate, load_fixtures, write_fixtures
from .schema import AdversarialScenario, ExpectedOutcome, ToolCallStep


def test_registry_covers_exactly_the_six_g9_required_classes():
    assert set(ATTACK_CLASS_REGISTRY) == set(AttackClass)
    assert len(AttackClass) == 6


@pytest.mark.parametrize("attack_class", list(AttackClass))
def test_generate_produces_at_least_one_real_scenario(attack_class):
    scenarios = generate(attack_class, count=4, seed=42)
    assert len(scenarios) >= 1
    assert all(s.attack_class == attack_class for s in scenarios)
    assert all(s.calls for s in scenarios)  # every scenario scripts at least one call


@pytest.mark.parametrize("attack_class", list(AttackClass))
def test_generate_is_reproducible_for_a_fixed_seed(attack_class):
    first = generate(attack_class, count=4, seed=42)
    second = generate(attack_class, count=4, seed=42)
    assert first == second


def test_generate_ids_are_unique_within_a_class():
    scenarios = generate(AttackClass.PROMPT_INJECTION_VIA_TOOL_OUTPUT, count=4, seed=42)
    ids = [s.id for s in scenarios]
    assert len(ids) == len(set(ids))


def test_scenario_round_trips_through_jsonl(tmp_path):
    scenario = AdversarialScenario(
        id="example-001",
        attack_class=AttackClass.UNAUTHORIZED_WRITE,
        description="agent calls a write tool with no prior HITL approval",
        calls=[ToolCallStep(server="hello-echo", tool="hitl_tool", args={})],
        expected=ExpectedOutcome(status="HELD", policy_fired="hello-echo-hitl-test-tool"),
    )
    path = tmp_path / "example.jsonl"

    write_fixtures([scenario], path)
    loaded = load_fixtures(path)

    assert loaded == [scenario]


def test_expected_outcome_rejects_an_unreal_status():
    with pytest.raises(ValueError, match="is not a real audit status"):
        ExpectedOutcome(status="NOT_A_REAL_STATUS")
