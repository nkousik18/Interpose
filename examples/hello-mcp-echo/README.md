# hello-mcp-echo

The smallest possible MCP server + client, used to prove the MCP Python SDK works before any
Interpose-specific code exists. See `concepts/09-mcp-handshake-and-transports.md` for what this
demonstrates conceptually.

Run it:

```
uv run python client.py
```

`client.py` launches `server.py` as a subprocess itself (over the stdio transport, see the
concept doc) — you don't need to run the server separately.
