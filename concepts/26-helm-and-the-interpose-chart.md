# Helm: templated Kubernetes manifests, and why the chart looks the way it does

Phase 2 Day 9 (`docs/ROADMAP.md`); implements `docs/INTERPOSE_SCOPING.md` Section 11.4.
First real Kubernetes *deployment* of Interpose — [[07-what-is-kubernetes]] introduced
what Kubernetes orchestrates and got `kind` running back in Phase 0, but nothing had
actually been deployed to it yet.

## What Helm actually is

A Kubernetes Deployment, Service, ConfigMap, Secret, and so on are each just a YAML
file you `kubectl apply`. For one service that's fine. Interpose's stack needs a
gateway Deployment, a Service, two ConfigMaps, a Secret, a migration Job, and
(optionally) Postgres, Redis, and Grafana — each with their own Deployment/Service/PVC.
Applying a dozen-plus YAML files by hand, keeping them consistent (same labels, same
naming, same environment-specific tweaks) across a laptop, CI, and eventually a real
AWS cluster, is exactly the kind of repetitive, error-prone work a real templating
tool exists to remove.

**Helm** is a package manager for Kubernetes. A **chart** is the package: a directory
of YAML templates (`charts/interpose/templates/`) plus one `values.yaml` file of
knobs. `helm install` renders every template with a given set of values and applies
the result. `helm upgrade` does the same against an existing **release** (a named,
tracked instance of a chart — you could `helm install` the same chart twice under two
release names into two namespaces and get two independent stacks). Compare to
alternatives: raw `kubectl apply -f` (no templating, no environment overlays, no
release tracking); Kustomize (patch-based overlays, ships inside `kubectl` itself, but
patching is a different mental model than templating with real variables); Helm won
here mainly because it's the ecosystem default — most real-world charts you'd install
alongside your own (cert-manager, ingress-nginx, Bitnami anything) are Helm charts, so
fluency in it is the more transferable skill.

**Go templates, not a new language.** Helm's templating is Go's `text/template`
syntax with some added functions (`include`, `toYaml`, `.Files.Glob`, `required`, …)
and a few implicit variables per file: `.Values` (whatever `values.yaml` plus any
`-f`/`--set` overrides resolved to), `.Release` (name, namespace, …), `.Chart`
(name, version), `.Files` (read-only access to other files *inside the chart
directory* — see `configmap-policies.yaml`, which reads `files/policies/*.yaml` this
way to build the demo policy pack into a ConfigMap, one key per file, without
duplicating that content into `values.yaml` as an ugly embedded blob).

## `_helpers.tpl` and why every name goes through a function

`{{ include "interpose.fullname" . }}` appears in nearly every template instead of a
literal string like `interpose`. Two reasons: (1) the same release can be installed
multiple times with different `--release-name`s (a second demo environment, a
different developer's kind cluster) — hardcoding a name would make every install
collide; (2) it's one place to fix if the naming convention ever changes.
`interpose.selectorLabels` is the more consequential one — see the bug below.

## A real bug the live test caught: Service selectors need to be *precise*

`Deployment.spec.selector` and `Service.spec.selector` both work by label matching —
"route traffic to / manage every pod carrying these labels." The gateway, Postgres,
Redis, and Grafana Deployments in this chart all share the same
`app.kubernetes.io/name`/`app.kubernetes.io/instance` labels (correct — they're all
part of the same release). The first draft of the gateway's `Service` selected only on
those two labels. Kubernetes doesn't know "these two labels happen to also be shared
by three other Deployments" is a problem — it just matches every pod that has them,
which was *all four* Deployments' pods at once. `kubectl port-forward svc/...` doesn't
pick "the right" matching pod; it picks whichever one the API returns, which in the
live test was the Redis pod — so a port-forward meant to reach the gateway's `/healthz`
silently connected to Redis's raw TCP port 6379 instead and failed with a confusing
"pod does not have a named port 'http'" error.

The fix: every workload in this chart also carries a component label
(`app.kubernetes.io/component: gateway` / `postgres` / `redis` / `grafana`), and every
Service/Deployment selector includes it. The general lesson — shared labels are for
things that are genuinely shared (the release), and anything that needs to
*distinguish* one workload from its siblings needs its own label in the selector, not
just in a name — held up: this is precisely the class of bug `helm template` (which
just renders YAML, no cluster involved) can't catch, because rendering doesn't know
what a Service selector actually resolves to at runtime. Only a real `kubectl get
endpoints` against a real cluster showed it. Worth remembering as a reason `helm
template`/`helm lint` are necessary but not sufficient checks for a chart — see the
next section.

## Values layering, and the embedded-vs-external pattern

`values.yaml` holds chart defaults, written to lean toward how this chart would
actually run in production (external Postgres/Redis, no chart-created secrets).
`values-dev.yaml` is a small overlay (`helm install -f values.yaml -f values-dev.yaml`,
later files winning on conflicts) that turns on the dev-only conveniences: a
chart-created Secret from plaintext values, instead of one populated externally.

The `postgres.embedded` / `redis.embedded` boolean pattern is the same idea repeated:
`values.yaml`'s default (`true`, since that's what makes a bare `helm install` on kind
actually work standing alone) deploys a plain single-replica Postgres/Redis Deployment
this chart defines itself; flipping it to `false` and setting `postgres.host` points
the same gateway Deployment at RDS/ElastiCache without touching any other template.
Section 11.4 describes this same toggle implemented via optional **Bitnami
sub-charts** (a chart depending on other, published charts) rather than first-party
templates — deliberately not done that way here: an external chart-repo dependency
(version pinning, `helm dependency build` needing network access, upstream breaking
changes between Bitnami releases) buys nothing when production never uses the embedded
path anyway and the only thing being demonstrated is the toggle itself, not
sophistication in how dev-mode Postgres runs.

## ConfigMaps, Secrets, and probes — connecting back to earlier concepts

- **ConfigMaps** (`configmap-upstreams.yaml`, `configmap-policies.yaml`,
  `configmap-app.yaml`) are this chart's Kubernetes-native version of the local
  `config/upstreams.yaml` and `config/policies/*.yaml` files from
  [[15-fastapi-and-the-naive-proxy]] and [[16-policy-engine-composition]] — same
  content, mounted as files into the container instead of read from the working
  directory.
- **Secrets** hold `DATABASE_URL`/`REDIS_URL`/`GROQ_API_KEY` — the same values
  `interpose.config.Settings` ([[18-postgres-sqlalchemy-alembic]],
  [[24-narrative-generation-with-a-real-llm]]) already read from environment
  variables locally; `envFrom: secretRef` is just how those environment variables get
  into the container in Kubernetes instead of a `.env` file.
- **Liveness/readiness/startup probes** are Kubernetes' health-check contract:
  liveness answers "should this pod be restarted" (so `/healthz` deliberately checks
  nothing external — see its docstring in `app.py` — a transient Postgres blip
  shouldn't kill a healthy gateway process); readiness answers "should this pod
  receive traffic right now" (`/readyz` genuinely checks Postgres and Redis
  connectivity, added this session specifically because the chart needed something
  real to probe); startup gives slower first-boot work (policy-pack compilation, first
  DB connection against a Postgres pod that might still be starting) more time before
  the other two probes start counting failures.

## What didn't get built, and why that's a real decision, not a shortcut

Section 11.4/11.5's full chart is enterprise-sized: ingress, HPA, RBAC, NetworkPolicy,
PodMonitor, Spark CRDs, pod-security hardening (distroless, `readOnlyRootFilesystem`,
seccomp). Each of those either has no real dependency yet (no Prometheus operator
installed, so a PodMonitor scrapes nothing; no Spark-on-Kubernetes job exists) or no
real use yet (no ingress controller, since local dev reaches everything via `kubectl
port-forward`). Writing that YAML now would be untested-because-unexercised, which is
worse than not having it — see `charts/interpose/README.md`'s "named gaps" table for
the full list and reasoning per item. This mirrors a pattern the project has used
since Day 2 (the in-memory `RateLimiter` before Redis existed) and Day 6 (the deferred
`interpose:session:{agent_id}` hash): build what something real exercises, name what's
missing explicitly, and let each gap get closed exactly when the thing that needs it
arrives.

## Related

- [[07-what-is-kubernetes]]
- [[15-fastapi-and-the-naive-proxy]]
- [[16-policy-engine-composition]]
- [[18-postgres-sqlalchemy-alembic]]
- [[21-redis-and-the-hitl-hold]]
