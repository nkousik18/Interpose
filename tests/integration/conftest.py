"""Shared fixtures for gateway integration tests: runs the real gateway and real
upstream MCP servers as live subprocesses on real ports. See
test_gateway_naive_forward.py's module docstring for why real subprocesses rather
than an in-process ASGI test client.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from interpose.config import get_settings
from interpose.session.redis_client import create_sync_redis

REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_SCRIPT = REPO_ROOT / "examples" / "hello-mcp-http-echo" / "server.py"
OFAC_SERVER_SCRIPT = REPO_ROOT / "mcp-servers" / "ofac-sanctions" / "src" / "server.py"
OFAC_FIXTURES = REPO_ROOT / "mcp-servers" / "ofac-sanctions" / "tests" / "fixtures"


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


@pytest.fixture(scope="module")
def ofac_upstream_and_gateway():
    """Same shape as `upstream_and_gateway`, but with the OFAC sanctions server
    instead of the echo server -- pointed at small local fixture CSVs
    (OFAC_SDN_SOURCE/OFAC_ALT_SOURCE) rather than the real Treasury API, so this test
    suite never depends on a live government service being reachable."""
    ofac_env = {
        **os.environ,
        "OFAC_SDN_SOURCE": str(OFAC_FIXTURES / "sdn_sample.csv"),
        "OFAC_ALT_SOURCE": str(OFAC_FIXTURES / "alt_sample.csv"),
    }
    upstream = subprocess.Popen([sys.executable, str(OFAC_SERVER_SCRIPT)], env=ofac_env)
    gateway = subprocess.Popen([sys.executable, "-m", "interpose.gateway"], cwd=REPO_ROOT)
    try:
        _wait_for_port("127.0.0.1", 9002)
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
def clean_state():
    """Every test starts from an empty audit table and an empty HITL ticket queue.
    For audit, the hash chain's genesis check (interpose.audit.chain) only makes
    sense against a known, reproducible starting point; for Redis, a leftover ticket
    from a previous test could otherwise be picked up by _approve_shortly/
    _deny_shortly's "first pending ticket" logic in test_gateway_hitl.py."""
    engine = create_engine(get_settings().database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE audit_entries RESTART IDENTITY"))
    finally:
        engine.dispose()

    redis_conn = create_sync_redis(get_settings().redis_url)
    try:
        redis_conn.flushdb()
    finally:
        redis_conn.close()

    yield
