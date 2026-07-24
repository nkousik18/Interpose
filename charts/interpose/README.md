# charts/interpose

Helm chart for Interpose (docs/INTERPOSE_SCOPING.md Section 11.4). Built Phase 2 Day 9
(docs/ROADMAP.md); see `concepts/26-helm-and-the-interpose-chart.md` for the underlying
Helm concepts.

## Install (local dev, kind)

Normally done via `scripts/dev-up.sh`, not by hand:

```sh
kind create cluster --config kind.yaml
docker build -t interpose:dev .
kind load docker-image interpose:dev
helm install interpose ./charts/interpose -f charts/interpose/values-dev.yaml \
  --set llm.groqApiKey="$GROQ_API_KEY"   # optional -- see values-dev.yaml
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
- ConfigMaps for the routing table (`upstreams.yaml`) and the demo policy pack
  (`config/policies/*.yaml`), and a Secret for `DATABASE_URL`/`REDIS_URL`/
  `GROQ_API_KEY` (dev: chart-created via `secrets.createDev`; prod: externally
  managed, referenced via `secrets.existingSecretName`).

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
| `podmonitor.yaml` + Prometheus | Nothing exports `/metrics` yet (no `prometheus-client`/OTel instrumentation built) and no Prometheus is deployed to scrape it -- see each dashboard JSON's "how to read" panel. Phase 3/4. |
| `crds/` (SparkApplication) | No Spark-on-Kubernetes job exists yet -- Spark today only runs `local[*]` for the one-off AML subsampling job (Phase 0). Real target is Phase 3's telemetry aggregation job. |
| Pod-security hardening (distroless base, `readOnlyRootFilesystem`, seccomp profile) | The image is already non-root (`runAsUser: 10001`, enforced in both Deployment and Job `securityContext`), which is the cheap, real part. Distroless specifically risks breaking the migration Job's `sh -c` invocation without a real payoff yet -- worth doing once the chart is otherwise stable, not while it's still changing weekly. |
| `values-prod.yaml`, GitHub Pages chart publishing | No production registry or target cluster exists yet -- Phase 4 (EKS + Terraform). |
| Bitnami Postgres/Redis sub-charts | Deliberately not used at all, not just deferred -- see `values.yaml`'s `postgres.embedded` comment. |

## Values

See `values.yaml` for the full annotated list. `values-dev.yaml` is the only
environment-specific overlay that exists today.
