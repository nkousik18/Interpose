# dev/mcp-servers

Plain Kubernetes manifests for upstream MCP servers used only in local kind dev, applied
directly with `kubectl apply -f dev/mcp-servers/` (per `docs/INTERPOSE_SCOPING.md` Section
11.3, step 5) rather than templated into `charts/interpose/`. The chart owns the actual
product (gateway + control plane + its dependencies); these are fixtures that give the
in-cluster gateway something real to route a call to.

`scripts/dev-up.sh` builds each server's image, `kind load docker-image`s it, and applies
these manifests after the `interpose-system` namespace exists. `scripts/dev-down.sh` needs no
matching cleanup step -- deleting the kind cluster takes everything in it with it.

- `hello-echo.yaml` -- the `examples/hello-mcp-http-echo` server (Deployment + Service,
  port 9001). Wired into the gateway's routing table via
  `charts/interpose/values-dev.yaml`'s `upstreams.servers.hello-echo`.
