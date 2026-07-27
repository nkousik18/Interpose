"""Tests for the fixture generator skeleton itself (Phase 2 Day 10) -- not
adversarial tests. Real per-attack-class tests land in Phase 4 once `generate()`
actually produces scenarios; see README.md.
"""

import pytest

from .attack_classes import ATTACK_CLASS_REGISTRY, AttackClass
from .generate import generate, load_fixtures, write_fixtures
from .schema import AdversarialScenario, ExpectedOutcome, ToolCallStep


def test_registry_covers_exactly_the_six_g9_required_classes():
    assert set(ATTACK_CLASS_REGISTRY) == set(AttackClass)
    assert len(AttackClass) == 6


@pytest.mark.parametrize("attack_class", list(AttackClass))
def test_generate_names_what_is_missing(attack_class):
    with pytest.raises(NotImplementedError) as exc_info:
        generate(attack_class, count=1, seed=42)
    assert ATTACK_CLASS_REGISTRY[attack_class].capability_needed in str(exc_info.value)


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
