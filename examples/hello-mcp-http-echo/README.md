# hello-mcp-http-echo

The same `echo` tool as `examples/hello-mcp-echo`, but served over the streamable-HTTP
transport instead of stdio. This is the transport Interpose's gateway actually proxies
(scoping doc Section 6.17), so this is the trivial upstream server used to test the
gateway's naive-forward path — see `tests/integration/test_gateway_naive_forward.py`.

Run it standalone (not needed for the integration test, which starts it itself):

```
uv run python server.py
```

Listens on `http://127.0.0.1:9001/mcp`.
