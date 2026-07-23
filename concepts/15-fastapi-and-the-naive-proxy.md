# FastAPI, and the gateway's first (naive) proxy

## What FastAPI is

FastAPI is a Python web framework: it turns incoming HTTP requests into calls to
Python functions you write ("route handlers") and turns what those functions return
into HTTP responses. It's built on **Starlette** (the actual ASGI toolkit doing
routing/middleware/streaming) and **Pydantic** (the same validation library already
used elsewhere in this project) — FastAPI's main contribution is gluing those two
together with type hints, so a function's parameter types double as request
validation. It's async-native: route handlers are `async def` functions that can
`await` other async work (like an outbound HTTP call) without blocking the whole
server while waiting.

**Why FastAPI here, specifically.** The scoping doc (Section 6.4) chose it over
alternatives like Starlette-directly, aiohttp, or Litestar because the MCP Python SDK
already assumes an ASGI-style async app, and because Pydantic models can be reused
directly between "validate this HTTP request" and "validate this policy YAML" — one
validation library end to end, not two.

## What "the gateway" means concretely, so far

Interpose's whole premise ([[02-interpose-gateway-overview]]) is sitting *between* an
MCP client (an agent) and an MCP server, so neither has to know Interpose is there.
As of Phase 1 Day 1, the gateway is a FastAPI app with exactly one route,
`/mcp/{server_name}`, that does four things per request (see
`src/interpose/gateway/app.py`):

1. **Ingress** — assigns a request ID, reads whatever agent/correlation identity is on
   the request, logs it.
2. **Parse** — validates the request body as a real MCP JSON-RPC envelope (using the
   MCP SDK's own `JSONRPCMessage` type, so a malformed request gets rejected before it
   ever reaches an upstream server).
3. **Route resolution** — looks up `{server_name}` in a small YAML file
   (`config/upstreams.yaml`) to find the real upstream server's URL. Unknown name → 404.
4. **Forward** — relays the request to that upstream via `httpx`, and streams the
   response straight back.

Nothing about policy, audit, or governance exists yet — every request that resolves to
a known upstream goes straight through unchanged. That's deliberate: this is Day 1 of
Section 6.5's nine-stage request lifecycle (Stages 1-3, then straight to 7-9, skipping
4-6 entirely). Full lifecycle in `docs/INTERPOSE_SCOPING.md` Section 6.5.

## Why the response has to be streamed, not just forwarded

The natural-looking implementation — call the upstream, get its full response, send
that back — breaks for one specific reason: MCP's streamable-HTTP transport
([[09-mcp-handshake-and-transports]]) doesn't only use request/response. After
`initialize`, the client also opens a long-lived `GET` request to receive
server-initiated messages, and that connection is *supposed* to stay open
indefinitely. If the gateway waited to collect "the whole response" before replying,
it would wait forever on that connection, because there is no "whole" — it's a stream,
not a single message.

So the gateway's forwarding function (`_forward` in `app.py`) uses `httpx`'s streaming
mode and relays bytes chunk-by-chunk as they arrive, in both directions, via FastAPI's
`StreamingResponse`. This works uniformly for both cases — a normal single-JSON-object
tool-call response looks like a "stream" of exactly one chunk — without the gateway
needing to know in advance which kind of exchange it's looking at.

## ConfigMap-driven routing, before there's a ConfigMap

Section 6.5's Stage 3 calls the routing source a "ConfigMap" — that's a Kubernetes
concept for injecting configuration into a running pod, and Interpose doesn't deploy
to Kubernetes until Phase 2. Locally, `config/upstreams.yaml` plays that same role: a
small file mapping route names to upstream URLs, loaded once at startup. When the Helm
chart exists, this file's content becomes a real ConfigMap manifest; the application
code that reads it (`src/interpose/gateway/routing.py`) won't need to change, only
where the YAML comes from.

## What was actually proven, and how

`tests/integration/test_gateway_naive_forward.py` runs the real gateway and a real
trivial upstream MCP server (`examples/hello-mcp-http-echo/`) as two live subprocesses
on real ports, then drives a genuine MCP client through the gateway: `initialize` →
`list_tools` → `call_tool("echo", ...)`. This intentionally avoids FastAPI's in-process
test client, because the long-lived GET-stream behavior above only shows up against a
real live server — an in-process mock could hide a proxy that looks correct but would
hang the moment a real streaming client touched it.

## Related

- [[01-what-is-mcp]]
- [[02-interpose-gateway-overview]]
- [[09-mcp-handshake-and-transports]]
