"""Unit tests for interpose.policies.loader -- YAML -> Policy, and pack loading."""

from pathlib import Path

import pytest

from interpose.policies.loader import load_policy_file, load_policy_pack
from interpose.policies.schema import AllowlistEffect, DenylistEffect

ALLOWLIST_YAML = """
policy: read-only-allowlist
description: Only read tools are permitted on ofac-sanctions.
applies_to:
  server: ofac-sanctions
  tools: [check_name]
effect:
  type: allowlist
"""

DENYLIST_YAML = """
policy: no-deletes
applies_to:
  server: transaction-graph
  tools: [delete_record]
effect:
  type: denylist
  reason: irreversible
audit:
  severity: high
  tag: [aml, write]
"""

MALFORMED_YAML = """
policy: missing-effect
applies_to:
  server: x
  tools: ["*"]
"""


def _write(path: Path, name: str, content: str) -> Path:
    file = path / name
    file.write_text(content)
    return file


class TestLoadPolicyFile:
    def test_loads_allowlist_policy(self, tmp_path: Path) -> None:
        file = _write(tmp_path, "allowlist.yaml", ALLOWLIST_YAML)
        policy = load_policy_file(file)
        assert policy.policy == "read-only-allowlist"
        assert isinstance(policy.effect, AllowlistEffect)

    def test_loads_denylist_policy_with_audit_meta(self, tmp_path: Path) -> None:
        file = _write(tmp_path, "denylist.yaml", DENYLIST_YAML)
        policy = load_policy_file(file)
        assert isinstance(policy.effect, DenylistEffect)
        assert policy.audit.severity == "high"
        assert policy.audit.tag == ["aml", "write"]

    def test_raises_on_malformed_policy(self, tmp_path: Path) -> None:
        file = _write(tmp_path, "malformed.yaml", MALFORMED_YAML)
        with pytest.raises(Exception):  # noqa: B017 -- pydantic ValidationError
            load_policy_file(file)


class TestLoadPolicyPack:
    def test_loads_all_yaml_files_in_directory(self, tmp_path: Path) -> None:
        _write(tmp_path, "a-allowlist.yaml", ALLOWLIST_YAML)
        _write(tmp_path, "b-denylist.yaml", DENYLIST_YAML)
        policies = load_policy_pack(tmp_path)
        assert {p.policy for p in policies} == {"read-only-allowlist", "no-deletes"}

    def test_empty_directory_yields_empty_list(self, tmp_path: Path) -> None:
        assert load_policy_pack(tmp_path) == []

    def test_ignores_non_yaml_files(self, tmp_path: Path) -> None:
        _write(tmp_path, "allowlist.yaml", ALLOWLIST_YAML)
        _write(tmp_path, "README.md", "not a policy")
        policies = load_policy_pack(tmp_path)
        assert len(policies) == 1

    def test_raises_on_duplicate_policy_names(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.yaml", ALLOWLIST_YAML)
        duplicate = ALLOWLIST_YAML.replace(
            "applies_to:\n  server: ofac-sanctions",
            "applies_to:\n  server: transaction-graph",
        )
        _write(tmp_path, "b.yaml", duplicate)
        with pytest.raises(ValueError, match="duplicate policy name"):
            load_policy_pack(tmp_path)
