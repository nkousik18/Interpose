#!/usr/bin/env python3
"""Runs every generated adversarial scenario for every attack class through a real
gateway (same machinery `tests/adversarial/test_live_scenarios.py` uses in CI) and
writes a JSON report -- the "evaluation report JSON" release deliverable
docs/INTERPOSE_SCOPING.md Section 4.6 (Category D: "Multi-agent evaluation... Eval
harness in CI") and Section 14.8 (Day 20: "evaluation report JSON attached") both
reference, but that `docs/ROADMAP.md` never actually scheduled building anywhere --
closed as part of Phase 4's adversarial-suite work rather than left as a claim
nothing backs up.

Deliberately not a new "evaluation" concept built from scratch: this project already
has exactly the machinery Section 12.2 describes evaluation needing (a harness that
runs scripted scenarios through the real system and checks a pass/fail outcome) --
`tests/adversarial/`'s own harness, built for a different *purpose* (a live security
claim, checked in CI) but the identical *mechanism* a regression-detection eval
harness needs. This script is that same mechanism, pointed at report generation
instead of raising pytest failures.

Usage:
    uv run python scripts/run_eval_report.py [--out PATH] [--count N] [--seed N]

Exits non-zero if any scenario failed -- usable as a CI gate on its own, though the
`adversarial` GitHub Actions job (.github/workflows/ci.yml) is the actual enforcement
today; this script's primary job is producing the durable JSON artifact.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests.adversarial.attack_classes import AttackClass  # noqa: E402
from tests.adversarial.generate import generate  # noqa: E402
from tests.adversarial.harness import (  # noqa: E402
    assert_scenario_result,
    run_scenario,
    scenario_gateway,
)


async def _run_class(attack_class: AttackClass, count: int, seed: int) -> list[dict[str, Any]]:
    scenarios = generate(attack_class, count=count, seed=seed)
    results: list[dict[str, Any]] = []
    async with scenario_gateway(attack_class) as gateway_url:
        for scenario in scenarios:
            entry: dict[str, Any] = {
                "id": scenario.id,
                "attack_class": attack_class.value,
                "description": scenario.description,
            }
            try:
                result = await run_scenario(scenario, gateway_url)
                assert_scenario_result(scenario, result)
                entry["passed"] = True
                entry["error"] = None
            except AssertionError as exc:
                entry["passed"] = False
                entry["error"] = str(exc)
            results.append(entry)
    return results


async def _run_all(count: int, seed: int) -> dict[str, Any]:
    all_results: list[dict[str, Any]] = []
    for attack_class in AttackClass:
        all_results.extend(await _run_class(attack_class, count, seed))

    total = len(all_results)
    passed = sum(1 for r in all_results if r["passed"])
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "scenarios_per_class": count,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "attack_classes_covered": len(AttackClass),
        },
        "results": all_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "eval_report.json")
    parser.add_argument("--count", type=int, default=4, help="scenarios per attack class")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    report = asyncio.run(_run_all(args.count, args.seed))
    args.out.write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    print(
        f"eval report: {summary['passed']}/{summary['total']} scenarios passed "
        f"across {summary['attack_classes_covered']} attack classes -> {args.out}"
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
