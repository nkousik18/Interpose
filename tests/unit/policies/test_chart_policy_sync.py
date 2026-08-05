"""Guards against `charts/interpose/files/policies-*/` silently drifting from its
source of truth. Helm's `.Files.Glob` can only read files inside the chart directory
(docs/project/SESSION_LOG.md, Phase 3 Day 15's in-cluster AML gap fix), so both the
Day 9/10 hello-echo demo pack and the real Phase 3 AML pack are checked-in copies,
not live references -- nothing but this test stops them from going stale.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHART_FILES = REPO_ROOT / "charts" / "interpose" / "files"


def _assert_dirs_match(source: Path, chart_copy: Path) -> None:
    source_files = {f.name: f for f in source.glob("*.yaml")}
    copy_files = {f.name: f for f in chart_copy.glob("*.yaml")}
    assert source_files.keys() == copy_files.keys(), (
        f"{chart_copy} has drifted from {source}: "
        f"missing {source_files.keys() - copy_files.keys()}, "
        f"extra {copy_files.keys() - source_files.keys()}"
    )
    for name, source_file in source_files.items():
        assert source_file.read_text() == copy_files[name].read_text(), (
            f"{chart_copy / name} content differs from {source_file}"
        )


def test_hello_echo_chart_copy_matches_config_policies() -> None:
    _assert_dirs_match(
        REPO_ROOT / "config" / "policies",
        CHART_FILES / "policies-hello-echo",
    )


def test_aml_chart_copy_matches_the_real_pack() -> None:
    _assert_dirs_match(
        REPO_ROOT / "policies" / "packs" / "aml",
        CHART_FILES / "policies-aml",
    )
