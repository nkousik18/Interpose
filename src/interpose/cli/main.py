"""The `interpose` CLI. First command: `verify-audit` (Section 6.7 / G3).

Run with: `uv run interpose verify-audit [--since YYYY-MM-DD]`
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

import typer
from sqlalchemy import create_engine, select

from interpose.audit.chain import verify_chain
from interpose.audit.models import AuditEntry
from interpose.config import get_settings

app = typer.Typer(add_completion=False, help="Interpose: audit and policy gateway for MCP.")


@app.callback()
def _callback() -> None:
    """Interpose: audit and policy gateway for MCP.

    An explicit (empty) group callback -- without one, Typer collapses a
    single-command app into a flat CLI (`interpose --since ...` instead of
    `interpose verify-audit --since ...`). More commands land here (e.g. `review`
    in Phase 2's HITL work), at which point this stops being load-bearing but is
    harmless to leave.
    """


def _fetch_all_entries(database_url: str) -> list[dict]:
    """Every audit entry, ordered by id (= chain order). Not filtered by date here --
    see verify_audit's docstring for why the whole chain always gets verified."""
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(select(AuditEntry).order_by(AuditEntry.id)).all()
            columns = [c.name for c in AuditEntry.__table__.columns]
            return [dict(zip(columns, row, strict=True)) for row in rows]
    finally:
        engine.dispose()


@app.command("verify-audit")
def verify_audit(
    since: Annotated[
        str | None,
        typer.Option(
            help=(
                "YYYY-MM-DD. Only report which entries fall at or after this date. Does "
                "NOT skip verifying earlier history -- a hash chain only proves integrity "
                "walked from genesis; checking a slice in isolation can't detect tampering "
                "outside that slice. See concepts/19-hash-chained-audit-log.md."
            )
        ),
    ] = None,
) -> None:
    """Walk the whole audit log from genesis; report the first hash-chain mismatch."""
    since_date: date | None = None
    if since is not None:
        try:
            since_date = date.fromisoformat(since)
        except ValueError as exc:
            typer.echo(f"invalid --since value {since!r}, expected YYYY-MM-DD: {exc}")
            raise typer.Exit(code=2) from exc

    entries = _fetch_all_entries(get_settings().database_url)

    if not entries:
        typer.echo("No audit entries found.")
        raise typer.Exit(code=0)

    result = verify_chain(entries)

    if not result.valid:
        typer.echo(f"FAILED: chain integrity broken at entry id={result.first_mismatch_id}.")
        typer.echo(result.detail or "")
        typer.echo(f"Verified {result.checked} of {len(entries)} entries before the break.")
        raise typer.Exit(code=1)

    typer.echo(f"OK: chain intact. {result.checked} entries verified from genesis.")
    if since_date is not None:
        cutoff = datetime(since_date.year, since_date.month, since_date.day, tzinfo=UTC)
        in_scope = sum(1 for e in entries if e["timestamp"] >= cutoff)
        typer.echo(f"{in_scope} of those entries are at or after {since_date.isoformat()}.")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
