"""`interpose demo aml` (docs/INTERPOSE_SCOPING.md Section 9.10, Phase 3 Day 15):
the scripted end-to-end AML demo. `--setup` provisions the local stack; `--run`
drives a real investigation through it and verifies the resulting audit trail --
the same two-step shape Section 9.10 describes.

Deliberately shells out to `scripts/dev-up.sh` and
`agents/aml-investigator/run_investigation.py` rather than reimplementing either --
`agents/` is its own component, outside `src/interpose/`'s module boundary (Section
6.16), and dev-up.sh is already the real, live-tested cluster-provisioning script
(Phase 2 Day 9). This command's job is to sequence and narrate those two existing
pieces, not duplicate them.

Run with:
  `uv run interpose demo aml --setup`
  `uv run interpose demo aml --run [--account-id ID] [--gateway-url URL]`
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from interpose.audit.chain import verify_chain
from interpose.cli._audit_query import fetch_all_entries
from interpose.config import get_settings

demo_app = typer.Typer(add_completion=False, help="Scripted end-to-end demos.")

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV_UP_SCRIPT = REPO_ROOT / "scripts" / "dev-up.sh"
INVESTIGATOR_SCRIPT = REPO_ROOT / "agents" / "aml-investigator" / "run_investigation.py"


@demo_app.command("aml")
def demo_aml(
    setup: Annotated[
        bool,
        typer.Option("--setup", help="Provision the local kind stack (scripts/dev-up.sh)."),
    ] = False,
    run: Annotated[
        bool,
        typer.Option("--run", help="Drive a real investigation and verify the audit trail."),
    ] = False,
    account_id: Annotated[
        str | None, typer.Option(help="Investigate this account instead of a seeded one.")
    ] = None,
    gateway_url: Annotated[
        str, typer.Option(help="Gateway base URL the investigation agent talks to.")
    ] = "http://127.0.0.1:8000",
) -> None:
    """Section 9.10's two-step demo script: `--setup` provisions, `--run` drives an
    investigation and verifies the audit trail. Can be combined in one invocation."""
    if not setup and not run:
        typer.echo("Specify --setup, --run, or both. See `interpose demo aml --help`.")
        raise typer.Exit(code=2)

    if setup:
        _run_setup()
    if run:
        _run_investigation(account_id, gateway_url)


def _run_setup() -> None:
    typer.echo("==> interpose demo aml --setup: provisioning the local kind stack")
    typer.echo(
        "    Provisions the gateway plus all three dev fixture MCP servers "
        "(hello-echo, ofac-sanctions, transaction-graph) in-cluster via "
        "scripts/dev-up.sh -- kind.yaml mounts $IBM_AML_DATA_DIR "
        "(default ~/.interpose/data/ibm-aml) into the cluster for transaction-graph, "
        "and the gateway loads the real AML policy pack "
        "(charts/interpose/files/policies-aml/, POLICY_PACK=aml). --run against this "
        "cluster's gateway (--gateway-url http://127.0.0.1:8000, the default) "
        "exercises the real AML pack end to end."
    )
    env = {**os.environ, "POLICY_PACK": "aml"}
    result = subprocess.run([str(DEV_UP_SCRIPT)], cwd=REPO_ROOT, env=env, check=False)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


def _run_investigation(account_id: str | None, gateway_url: str) -> None:
    typer.echo(f"==> interpose demo aml --run: investigating against {gateway_url}")
    cmd = [sys.executable, str(INVESTIGATOR_SCRIPT), "--gateway-url", gateway_url]
    if account_id:
        cmd += ["--account-id", account_id]
    result = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        typer.echo("Investigation run failed; skipping audit verification.")
        raise typer.Exit(code=result.returncode)

    typer.echo("==> verifying the audit trail (same check as `interpose verify-audit`)")
    entries = fetch_all_entries(get_settings().database_url)
    if not entries:
        typer.echo("No audit entries found.")
        raise typer.Exit(code=1)

    chain_result = verify_chain(entries)
    if not chain_result.valid:
        typer.echo(f"FAILED: chain integrity broken at entry id={chain_result.first_mismatch_id}.")
        raise typer.Exit(code=1)

    typer.echo(f"OK: chain intact. {chain_result.checked} entries verified from genesis.")
    typer.echo(
        "==> Grafana dashboards (Section 12.4): "
        "kubectl port-forward -n interpose-system svc/interpose-grafana 3000:3000, "
        "then http://localhost:3000"
    )
    raise typer.Exit(code=0)
