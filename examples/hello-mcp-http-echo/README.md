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

## In-cluster (kind)

Also deployed as a real dev fixture inside the kind cluster via
`dev/mcp-servers/hello-echo.yaml`, built from this directory's `Dockerfile` and applied
automatically by `scripts/dev-up.sh` -- see `dev/mcp-servers/README.md`. This gives the
kind-deployed gateway a genuine upstream to route `/mcp/hello-echo` to, instead of only
ever being exercised via docker-compose or bare subprocesses. Inside the container it
binds to `0.0.0.0` (`MCP_ECHO_HOST=0.0.0.0`, set by the Dockerfile) instead of the
`127.0.0.1` default used for local/subprocess runs -- see the comment in `server.py`.
