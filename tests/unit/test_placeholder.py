"""First real test in the repo: proves the package imports and pytest is wired up
correctly in CI. Gets replaced by real coverage as gateway/policy/audit code lands."""

import interpose


def test_package_imports() -> None:
    assert interpose is not None
