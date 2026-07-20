# The MCP handshake, and what "transport" means

Follows [[01-what-is-mcp]] — this is what we learned by actually running a client and server
against each other in `examples/hello-mcp-echo/`.

## What a "transport" is

MCP defines *what* messages look like (tool discovery, tool calls, results — all JSON-RPC
under the hood) but not *how the bytes get from one process to another*. That second part is
the transport. Two matter for us:

- **stdio**: the client launches the server as a local subprocess and talks to it over its
  standard input/output streams — the same stdin/stdout every command-line program has. No
  network involved at all. This is what `examples/hello-mcp-echo/client.py` used: it started
  `server.py` itself as a child process.
- **Streamable HTTP**: client and server are separate processes (possibly on separate
  machines), talking over a normal HTTP connection. This is what Interpose's gateway will use in
  production — the gateway can't be a subprocess of every agent that talks to it.

The scoping doc's decision (Section 6.17) is "Streamable HTTP first, stdio in v0.2 for local
dev convenience" for the *gateway* — but stdio is exactly the right transport for this
hello-world, and for real MCP servers run purely for local development.

## What actually happened when we ran it

Watch the sequence in `client.py`:

1. **Launch**: `stdio_client(params)` starts `server.py` as a subprocess and wires up its
   stdin/stdout as the communication channel.
2. **`session.initialize()`** — the handshake. Client and server exchange protocol versions and
   capabilities before doing anything else, the same idea as a TLS handshake or an HTTP
   `OPTIONS` preflight: agree on the ground rules first. If this succeeds, both sides know
   they're speaking compatible MCP.
3. **`session.list_tools()`** — the client asks "what can you do?" The server responds with its
   tool catalog: names, descriptions, input schemas. This is how an LLM-driven agent knows
   `echo` exists and what argument it takes, without any hardcoded knowledge of this specific
   server.
4. **`session.call_tool("echo", {"text": ...})`** — the actual invocation: tool name plus a
   JSON object of arguments matching that tool's schema. The server runs the corresponding
   Python function and returns a result.

The printed output confirmed each step: the tool catalog came back as `['echo']`, and the call
returned exactly the text we sent, unchanged.

## Why this was worth doing before writing any gateway code

Interpose's entire job is to sit *between* an exchange like this one — impersonating a server to
the real client, and a client to the real server, without either side needing to know Interpose
is there. Having actually run a real client and real server talking directly to each other
first means we now know what "normal" looks like, which makes it much easier to tell, once the
gateway exists, whether it's faithfully proxying that exchange or subtly breaking it.

## Related

- [[01-what-is-mcp]]
- [[02-interpose-gateway-overview]]
