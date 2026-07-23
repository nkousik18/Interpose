"""The `interpose` CLI: `verify-audit` (Section 6.7 / G3) and `review` (Section 6.8 /
Phase 2 Day 6 -- list/approve/deny pending HITL tickets).

Run with:
  `uv run interpose verify-audit [--since YYYY-MM-DD]`
  `uv run interpose review list`
  `uv run interpose review approve <ticket-id> --reviewer NAME --rationale "..."`
  `uv run interpose review deny <ticket-id> --reviewer NAME --rationale "..."`
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

import typer
from sqlalchemy import create_engine, select

from interpose.audit.chain import verify_chain
from interpose.audit.models import AuditEntry
from interpose.config import get_settings
from interpose.session import hitl
from interpose.session.redis_client import create_sync_redis

app = typer.Typer(add_completion=False, help="Interpose: audit and policy gateway for MCP.")
review_app = typer.Typer(add_completion=False, help="List and decide pending HITL tickets.")
app.add_typer(review_app, name="review")


@app.callback()
def _callback() -> None:
    """Interpose: audit and policy gateway for MCP.

    An explicit (empty) group callback -- without one, and if `review` were ever the
    only subcommand group, Typer would collapse a single-command app into a flat CLI
    (`interpose --since ...` instead of `interpose verify-audit --since ...`). Harmless
    to leave now that there are two command groups regardless.
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


@review_app.command("list")
def review_list() -> None:
    """List pending HITL tickets (server, tool, agent, reviewer group, age)."""
    conn = create_sync_redis(get_settings().redis_url)
    try:
        tickets = hitl.list_pending(conn)
    finally:
        conn.close()

    if not tickets:
        typer.echo("No pending tickets.")
        raise typer.Exit(code=0)

    for t in tickets:
        created = datetime.fromtimestamp(t.created_at, tz=UTC).isoformat()
        typer.echo(
            f"{t.ticket_id}  server={t.server} tool={t.tool} agent={t.agent_id} "
            f"reviewer_group={t.reviewer_group} created_at={created}"
        )
    raise typer.Exit(code=0)


@review_app.command("approve")
def review_approve(
    ticket_id: str,
    reviewer: Annotated[str, typer.Option(help="Who is approving this.")],
    rationale: Annotated[
        str, typer.Option(help="Why -- required, becomes part of the audit trail.")
    ],
) -> None:
    """Approve a held tool call; it will be forwarded to the upstream server."""
    _decide(ticket_id, "APPROVED", reviewer, rationale)


@review_app.command("deny")
def review_deny(
    ticket_id: str,
    reviewer: Annotated[str, typer.Option(help="Who is denying this.")],
    rationale: Annotated[
        str, typer.Option(help="Why -- required, becomes part of the audit trail.")
    ],
) -> None:
    """Deny a held tool call; it will never be forwarded."""
    _decide(ticket_id, "DENIED", reviewer, rationale)


def _decide(ticket_id: str, status: str, reviewer: str, rationale: str) -> None:
    conn = create_sync_redis(get_settings().redis_url)
    try:
        result = hitl.decide_ticket(
            conn, ticket_id, status=status, decided_by=reviewer, rationale=rationale
        )
    finally:
        conn.close()

    if result is None:
        typer.echo(f"No such ticket: {ticket_id} (already expired, or never existed).")
        raise typer.Exit(code=1)

    ticket, applied = result
    if not applied:
        typer.echo(
            f"Ticket {ticket_id} was already decided: {ticket.status} by "
            f"{ticket.decided_by} ({ticket.rationale!r}). Not overwritten."
        )
        raise typer.Exit(code=1)

    typer.echo(f"Ticket {ticket_id}: {ticket.status} by {reviewer}.")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
