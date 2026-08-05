# charts/interpose

Helm chart for Interpose (docs/INTERPOSE_SCOPING.md Section 11.4). Built Phase 2 Day 9
(docs/ROADMAP.md); see `concepts/26-helm-and-the-interpose-chart.md` for the underlying
Helm concepts.

## Install (local dev, kind)

Normally done via `scripts/dev-up.sh`, not by hand:

```sh
export IBM_AML_DATA_DIR="$HOME/.interpose/data/ibm-aml"   # transaction-graph's dataset
envsubst '$IBM_AML_DATA_DIR' < kind.yaml | kind create cluster --config -
docker build -t interpose:dev .
docker build -t hello-echo:dev examples/hello-mcp-http-echo
docker build -t ofac-sanctions:dev mcp-servers/ofac-sanctions
docker build -t transaction-graph:dev mcp-servers/transaction-graph
kind load docker-image interpose:dev hello-echo:dev ofac-sanctions:dev transaction-graph:dev
kubectl create namespace interpose-system
kubectl apply -f dev/mcp-servers/     # dev fixture MCP servers, see dev/mcp-servers/README.md
helm install interpose ./charts/interpose -f charts/interpose/values-dev.yaml \
  --set llm.groqApiKey="$GROQ_API_KEY" \   # optional -- see values-dev.yaml
  --set policies.pack=aml                  # or "hello-echo" (default), see values.yaml
```

## What this chart actually deploys

- **`interpose` Deployment** -- the gateway process, which includes the in-process
  LangGraph control-plane loop (Day 7's `run_forever` background task). One
  Deployment, not the two Section 11.5 describes -- see `values.yaml`'s
  `replicaCount` comment for the full reasoning.
- **`interpose-postgres` / `interpose-redis`** -- first-party (not Bitnami sub-chart)
  single-replica Deployments for local dev, gated by `postgres.embedded` /
  `redis.embedded`. Production sets both to `false` and points at RDS/ElastiCache.
- **`interpose-migrate`** -- a `post-install,post-upgrade` Helm hook Job that runs
  `alembic upgrade head` against Postgres before anything else touches it.
- **`interpose-grafana`** -- Grafana with the four dashboards from Section 12.4
  provisioned automatically, gated by `grafana.enabled`.
- ConfigMaps for the routing table (`upstreams.yaml`) and a policy pack, whichever
  `values.yaml`'s `policies.pack` selects -- `files/policies-hello-echo/*.yaml` (the
  Day 9/10 demo pack, default) or `files/policies-aml/*.yaml` (the real Phase 3 AML
  pack). Both are checked-in copies of `config/policies/` and `policies/packs/aml/`
  respectively, kept in sync by hand and checked by
  `tests/unit/policies/test_chart_policy_sync.py` -- Helm's `.Files.Glob` can't read
  outside the chart directory. Also a Secret for `DATABASE_URL`/`REDIS_URL`/
  `GROQ_API_KEY` (dev: chart-created via `secrets.createDev`; prod: externally
  managed, referenced via `secrets.existingSecretName`).

**Not deployed by this chart, but wired into it in dev:** `values-dev.yaml` points
`upstreams.servers.{hello-echo,ofac-sanctions,transaction-graph}` at real in-cluster
MCP servers, applied via plain `kubectl apply -f dev/mcp-servers/` (see
`dev/mcp-servers/README.md`), not templated into this chart: `examples/hello-mcp-http-echo`
(the Day 9/10 fixture), and the real Phase 3 `mcp-servers/ofac-sanctions` and
`mcp-servers/transaction-graph`. That's what makes `/mcp/{name}` a genuine end-to-end
call through the kind-deployed gateway rather than a 404, without the chart owning a
workload that isn't part of the actual product.

## Named gaps (deliberately not built yet)

Per the Day 9 scoping conversation: Section 11.4/11.5 in full is enterprise-sized.
Some of it has no real dependency yet; some needs infrastructure this chart doesn't
install. Writing that YAML now would mean templates nothing exercises, not a
stronger deploy.

| Item | Why deferred |
|---|---|
| `ingress.yaml` | Local dev uses `kubectl port-forward`; no ingress controller installed by `dev-up.sh` (skips cert-manager + ingress-nginx entirely, unlike the doc's literal script). Real target is an ALB/nginx-ingress in front of the EKS reference deploy, Phase 4. |
| `rbac.yaml` (ConfigMap-watch Role) | The gateway loads policies once at startup; there's no hot-reload watch loop for it to grant permissions to yet (Day 2's "no reload trigger wired" gap, still open). |
| `networkpolicy.yaml` | No attacker model exercised yet to test egress restriction against -- meaningful once the adversarial test suite (Phase 4) exists. |
| `podmonitor.yaml` + Prometheus | Nothing exports `/metrics` yet (no `prometheus-client` instrumentation built) and no Prometheus is deployed to scrape it -- see each dashboard JSON's "how to read" panel. Phase 3/4. |
| OTel collector + Jaeger in-cluster | Day 10 wired real OpenTelemetry tracing into the gateway (`interpose.observability.tracing`) and Jaeger into `docker-compose.yaml`, but only for bare/docker-compose dev -- no OTel Collector DaemonSet or Jaeger Deployment exists in this chart yet, so a kind install has `otel_exporter_endpoint` unset and traces nothing. See `concepts/27-opentelemetry-and-distributed-tracing.md`. |
| `crds/` (SparkApplication) | No Spark-on-Kubernetes job exists yet -- Spark today only runs `local[*]` for the one-off AML subsampling job (Phase 0). Real target is Phase 3's telemetry aggregation job. |
| Pod-security hardening (distroless base, `readOnlyRootFilesystem`, seccomp profile) | The image is already non-root (`runAsUser: 10001`, enforced in both Deployment and Job `securityContext`), which is the cheap, real part. Distroless specifically risks breaking the migration Job's `sh -c` invocation without a real payoff yet -- worth doing once the chart is otherwise stable, not while it's still changing weekly. |
| `values-prod.yaml`, GitHub Pages chart publishing | No production registry or target cluster exists yet -- Phase 4 (EKS + Terraform). |
| Bitnami Postgres/Redis sub-charts | Deliberately not used at all, not just deferred -- see `values.yaml`'s `postgres.embedded` comment. |

## Values

See `values.yaml` for the full annotated list. `values-dev.yaml` is the only
environment-specific overlay that exists today.
