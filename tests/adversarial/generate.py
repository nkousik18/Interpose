"""Adversarial fixture generator (docs/INTERPOSE_SCOPING.md Section 10.5, G9).

Phase 2 Day 10 builds only the machinery -- scenario schema, attack-class registry,
JSONL round-trip -- with deliberately zero real scenarios yet. Two of the 6 required
classes still need a gateway capability that doesn't exist (a response-side policy
hook; a real `pii_redaction` implementation -- see attack_classes.py); writing
templates against the other four now, ahead of a scripted verification harness that
actually runs them through a live gateway, would just be untested prose. Real
generation is Phase 4 (Week 4) scope, once every listed gap is closed. Until then,
`generate()` raises `NotImplementedError` for every class, naming what's missing.
"""

from pathlib import Path

from .attack_classes import ATTACK_CLASS_REGISTRY, AttackClass
from .schema import AdversarialScenario

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def generate(attack_class: AttackClass, count: int, seed: int) -> list[AdversarialScenario]:
    """Produce `count` scenario variants for `attack_class` (seeded for reproducibility).

    Raises NotImplementedError today for every class -- see module docstring.
    """
    info = ATTACK_CLASS_REGISTRY[attack_class]
    raise NotImplementedError(
        f"{attack_class.value}: no fixture template yet -- needs {info.capability_needed}. "
        "See tests/adversarial/README.md."
    )


def write_fixtures(scenarios: list[AdversarialScenario], path: Path) -> None:
    with path.open("w") as f:
        for scenario in scenarios:
            f.write(scenario.model_dump_json())
            f.write("\n")


def load_fixtures(path: Path) -> list[AdversarialScenario]:
    scenarios = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            scenarios.append(AdversarialScenario.model_validate_json(line))
    return scenarios
