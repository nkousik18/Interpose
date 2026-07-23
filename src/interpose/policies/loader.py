"""YAML loading + validation for policy packs (docs/INTERPOSE_SCOPING.md Section 6.6).

Each policy is one YAML file; a policy pack (e.g. `policies/packs/aml/`) is a
directory of them.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from interpose.policies.schema import Policy


def load_policy_file(path: Path | str) -> Policy:
    raw = yaml.safe_load(Path(path).read_text())
    return Policy.model_validate(raw)


def load_policy_pack(path: Path | str) -> list[Policy]:
    """Load every `*.yaml` file in a directory as one Policy each.

    Raises ValueError if two files declare the same `policy` name -- policy names are
    referenced elsewhere (audit entries, `interpose review`) and must be unique.
    """
    files = sorted(Path(path).glob("*.yaml"))
    policies = [load_policy_file(f) for f in files]
    seen: dict[str, Path] = {}
    for policy, file in zip(policies, files, strict=True):
        if policy.policy in seen:
            raise ValueError(
                f"duplicate policy name {policy.policy!r} in {file} "
                f"(already used by {seen[policy.policy]})"
            )
        seen[policy.policy] = file
    return policies
