"""Shared fixture for gateway integration tests: runs the real gateway and the real
trivial upstream MCP server (examples/hello-mcp-http-echo/) as live subprocesses on
real ports. See test_gateway_naive_forward.py's module docstring for why real
subprocesses rather than an in-process ASGI test client.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from interpose.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_SCRIPT = REPO_ROOT / "examples" / "hello-mcp-http-echo" / "server.py"


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"nothing listening on {host}:{port} after {timeout}s")


@pytest.fixture(scope="module")
def upstream_and_gateway():
    upstream = subprocess.Popen([sys.executable, str(UPSTREAM_SCRIPT)])
    gateway = subprocess.Popen([sys.executable, "-m", "interpose.gateway"], cwd=REPO_ROOT)
    try:
        _wait_for_port("127.0.0.1", 9001)
        _wait_for_port("127.0.0.1", 8000)
        yield
    finally:
        for proc in (gateway, upstream):
            proc.terminate()
        for proc in (gateway, upstream):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


@pytest.fixture(autouse=True)
def clean_audit_table():
    """Every audit-touching test starts from an empty table -- the hash chain's
    genesis check (see interpose.audit.chain) only makes sense against a known,
    reproducible starting point."""
    engine = create_engine(get_settings().database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE audit_entries RESTART IDENTITY"))
    finally:
        engine.dispose()
    yield
