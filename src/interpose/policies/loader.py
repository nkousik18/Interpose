"""YAML loading + validation for policy packs (docs/INTERPOSE_SCOPING.md Section 6.6).

Each policy is one YAML file; a policy pack (e.g. `policies/packs/aml/`) is a
directory of them, plus one `pack.yaml` manifest (Section 9.8) describing the pack
itself -- name, version, regulation references, and the list of policy names it's
supposed to contain. `pack.yaml` is skipped when globbing for policies (it doesn't
parse as one), and its `policies` list is cross-checked against what's actually in
the directory: a manifest that's silently drifted from its own directory (a policy
renamed, added, or removed without updating it) is worse than no manifest at all.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from interpose.policies.schema import PackManifest, Policy

MANIFEST_FILENAME = "pack.yaml"


def load_policy_file(path: Path | str) -> Policy:
    raw = yaml.safe_load(Path(path).read_text())
    return Policy.model_validate(raw)


def load_pack_manifest(path: Path | str) -> PackManifest | None:
    """Returns None if the directory has no `pack.yaml` -- not every `policy_dir`
    (e.g. an ad hoc test fixture directory) is a named, versioned pack."""
    manifest_path = Path(path) / MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    return PackManifest.model_validate(yaml.safe_load(manifest_path.read_text()))


def load_policy_pack(path: Path | str) -> list[Policy]:
    """Load every `*.yaml` file in a directory as one Policy each, except
    `pack.yaml` itself.

    Raises ValueError if two files declare the same `policy` name -- policy names are
    referenced elsewhere (audit entries, `interpose review`) and must be unique -- or
    if a `pack.yaml` manifest's `policies` list doesn't exactly match the policy names
    actually found in the directory.
    """
    files = sorted(f for f in Path(path).glob("*.yaml") if f.name != MANIFEST_FILENAME)
    policies = [load_policy_file(f) for f in files]
    seen: dict[str, Path] = {}
    for policy, file in zip(policies, files, strict=True):
        if policy.policy in seen:
            raise ValueError(
                f"duplicate policy name {policy.policy!r} in {file} "
                f"(already used by {seen[policy.policy]})"
            )
        seen[policy.policy] = file

    manifest = load_pack_manifest(path)
    if manifest is not None:
        manifest_names = set(manifest.policies)
        directory_names = set(seen)
        missing = manifest_names - directory_names
        extra = directory_names - manifest_names
        if missing or extra:
            raise ValueError(
                f"{path}/{MANIFEST_FILENAME}'s policies list doesn't match the "
                f"directory contents: missing {sorted(missing)!r}, "
                f"unlisted extra {sorted(extra)!r}"
            )

    return policies
