#!/usr/bin/env bash
# Brings up the full Interpose stack on a local kind cluster: cluster -> images ->
# dev/mcp-servers/ fixtures -> Helm release -> port-forwards. Phase 2 Day 9
# (docs/ROADMAP.md); see charts/interpose/README.md for what the chart actually
# deploys, dev/mcp-servers/README.md for the fixture MCP server(s) it doesn't, and
# concepts/26-helm-and-the-interpose-chart.md for the concepts behind it.
#
# Deliberately skips two steps Section 11.3's literal script lists (cert-manager,
# ingress-nginx): local dev reaches everything via `kubectl port-forward`, so there's
# no TLS termination or ingress routing to stand up -- see charts/interpose/README.md's
# "named gaps" table.
#
# Idempotent: safe to re-run. Re-running against an existing cluster upgrades the
# Helm release in place rather than failing.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CLUSTER_NAME="interpose-dev"
NAMESPACE="interpose-system"
RELEASE="interpose"
PIDFILE="$REPO_ROOT/.dev-up.pids"
export IBM_AML_DATA_DIR="${IBM_AML_DATA_DIR:-$HOME/.interpose/data/ibm-aml}"

start=$(date +%s)

for bin in kind helm kubectl docker envsubst; do
  command -v "$bin" >/dev/null 2>&1 || {
    echo "error: $bin not found on PATH" >&2
    exit 1
  }
done

if [[ ! -d "$IBM_AML_DATA_DIR/transactions" || ! -d "$IBM_AML_DATA_DIR/accounts" ]]; then
  echo "error: IBM_AML_DATA_DIR ($IBM_AML_DATA_DIR) is missing transactions/ or accounts/" >&2
  echo "       run interpose.analytics.subsample_aml first (see data/README.md)" >&2
  exit 1
fi

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "==> kind cluster '$CLUSTER_NAME' already exists, reusing it"
  echo "    (extraMounts only apply at cluster creation -- if this cluster predates"
  echo "    transaction-graph's kind.yaml mount, delete it with scripts/dev-down.sh"
  echo "    and re-run this script)"
else
  echo "==> creating kind cluster '$CLUSTER_NAME' (mounting \$IBM_AML_DATA_DIR=$IBM_AML_DATA_DIR)"
  envsubst '$IBM_AML_DATA_DIR' < kind.yaml | kind create cluster --config -
fi

echo "==> building interpose:dev image"
docker build -t interpose:dev .

echo "==> building hello-echo:dev image (dev fixture MCP server)"
docker build -t hello-echo:dev examples/hello-mcp-http-echo

echo "==> building ofac-sanctions:dev image (dev fixture MCP server)"
docker build -t ofac-sanctions:dev mcp-servers/ofac-sanctions

echo "==> building transaction-graph:dev image (dev fixture MCP server)"
docker build -t transaction-graph:dev mcp-servers/transaction-graph

echo "==> loading images into kind"
kind load docker-image interpose:dev hello-echo:dev ofac-sanctions:dev transaction-graph:dev \
  --name "$CLUSTER_NAME"

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

echo "==> applying dev/mcp-servers/ (see dev/mcp-servers/README.md -- not part of the chart)"
kubectl apply -f dev/mcp-servers/

echo "==> helm upgrade --install"
helm_args=(upgrade --install "$RELEASE" ./charts/interpose \
  -f charts/interpose/values-dev.yaml \
  --namespace "$NAMESPACE" \
  --wait --timeout 5m)
if [[ -n "${GROQ_API_KEY:-}" ]]; then
  helm_args+=(--set "llm.groqApiKey=$GROQ_API_KEY")
else
  echo "    (GROQ_API_KEY not set -- control-plane narrative generation will use its non-LLM fallback)"
fi
POLICY_PACK="${POLICY_PACK:-hello-echo}"
helm_args+=(--set "policies.pack=$POLICY_PACK")
echo "    policy pack: $POLICY_PACK"
helm "${helm_args[@]}"

echo "==> waiting for dev fixture MCP servers to be ready"
kubectl wait --for=condition=available --timeout=60s -n "$NAMESPACE" deployment/hello-echo
kubectl wait --for=condition=available --timeout=60s -n "$NAMESPACE" deployment/ofac-sanctions
kubectl wait --for=condition=available --timeout=90s -n "$NAMESPACE" deployment/transaction-graph

echo "==> pod status"
kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE"
kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/component=dev-mcp-server"

: > "$PIDFILE"
echo "==> starting port-forwards (gateway :8000, grafana :3000)"
kubectl port-forward -n "$NAMESPACE" "svc/${RELEASE}-interpose" 8000:8000 \
  >"$REPO_ROOT/.dev-up-gateway-forward.log" 2>&1 &
echo $! >> "$PIDFILE"
kubectl port-forward -n "$NAMESPACE" "svc/${RELEASE}-interpose-grafana" 3000:3000 \
  >"$REPO_ROOT/.dev-up-grafana-forward.log" 2>&1 &
echo $! >> "$PIDFILE"
disown -a

sleep 2
end=$(date +%s)
echo
echo "==> up in $((end - start))s"
echo "    gateway:  http://127.0.0.1:8000/healthz"
echo "    grafana:  http://127.0.0.1:3000  (admin / admin)"
echo "    teardown: scripts/dev-down.sh"
