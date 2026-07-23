"""Same echo tool as examples/hello-mcp-echo, but served over the streamable-HTTP
transport instead of stdio -- this is the transport Interpose's gateway proxies (see
concepts/09-mcp-handshake-and-transports.md). Used as the trivial upstream server for
testing the gateway's naive-forward path (docs/ROADMAP.md Phase 1, Day 1) and, via
`dangerous_tool`, `throttled_tool`, and `hitl_tool`/`hitl_timeout_tool`, the policy
stage (Phase 1 Days 3/5, Phase 2 Day 6 -- see config/policies/).
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hello-echo-http", host="127.0.0.1", port=9001)


@mcp.tool()
def echo(text: str) -> str:
    """Return the input text unchanged."""
    return text


@mcp.tool()
def dangerous_tool() -> str:
    """A tool that only exists to be denylisted -- the gateway's policy config
    (config/policies/hello-echo-denylist.yaml) blocks it. If a test ever sees this
    tool actually execute, the policy stage isn't working."""
    return "should never be reached"


@mcp.tool()
def throttled_tool() -> str:
    """A tool that only exists to be rate-limited -- see
    config/policies/hello-echo-throttle.yaml."""
    return "called"


@mcp.tool()
def hitl_tool() -> str:
    """A tool that only exists to be HITL-gated -- see
    config/policies/hello-echo-hitl.yaml. Should only ever execute after an
    approval through `interpose review approve`."""
    return "approved and executed"


@mcp.tool()
def hitl_timeout_tool() -> str:
    """Same as hitl_tool, but its policy uses a very short timeout, so a test can
    exercise the "nobody reviewed it in time" path without waiting long."""
    return "should never be reached (nobody approves this one in the tests)"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
