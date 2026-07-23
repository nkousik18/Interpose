"""Phase 1, Day 5 acceptance test (docs/ROADMAP.md): the `interpose verify-audit` CLI
(Section 6.7 / G3) against a real Postgres audit log, not just chain.py in isolation.
"""

from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from interpose.cli.main import app
from interpose.config import get_settings

runner = CliRunner()


def test_empty_audit_log_reports_no_entries() -> None:
    result = runner.invoke(app, ["verify-audit"])
    assert result.exit_code == 0
    assert "No audit entries found" in result.output


async def test_valid_chain_reports_ok(upstream_and_gateway: None) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client("http://127.0.0.1:8000/mcp/hello-echo") as (
        read,
        write,
        _get_session_id,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("echo", {"text": "verified by CLI"})

    result = runner.invoke(app, ["verify-audit"])
    assert result.exit_code == 0
    assert "OK: chain intact. 2 entries verified from genesis." in result.output


async def test_tampered_chain_fails_with_nonzero_exit(upstream_and_gateway: None) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client("http://127.0.0.1:8000/mcp/hello-echo") as (
        read,
        write,
        _get_session_id,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("echo", {"text": "will be tampered"})

    engine = create_engine(get_settings().database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE audit_entries SET tool = 'tampered' WHERE id = 1"))
    finally:
        engine.dispose()

    result = runner.invoke(app, ["verify-audit"])
    assert result.exit_code == 1
    assert "FAILED: chain integrity broken at entry id=1" in result.output


def test_since_filter_reports_a_count_without_skipping_verification() -> None:
    result = runner.invoke(app, ["verify-audit", "--since", "2000-01-01"])
    assert result.exit_code == 0
    assert "No audit entries found" in result.output


def test_invalid_since_value_is_rejected() -> None:
    result = runner.invoke(app, ["verify-audit", "--since", "not-a-date"])
    assert result.exit_code == 2
