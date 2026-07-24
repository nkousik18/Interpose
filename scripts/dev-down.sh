#!/usr/bin/env bash
# Tears down what dev-up.sh brought up: kills the port-forwards it started, then
# deletes the kind cluster entirely (Section 11.3: "no residual state"). Deleting the
# cluster also takes the Helm release, both PVCs, and everything else with it -- there
# is deliberately no softer "just uninstall the release" mode here, since a stray
# kind cluster with no obvious purpose is the actual problem this guards against.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CLUSTER_NAME="interpose-dev"
PIDFILE="$REPO_ROOT/.dev-up.pids"

if [[ -f "$PIDFILE" ]]; then
  echo "==> stopping port-forwards"
  while read -r pid; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done < "$PIDFILE"
  rm -f "$PIDFILE" "$REPO_ROOT/.dev-up-gateway-forward.log" "$REPO_ROOT/.dev-up-grafana-forward.log"
fi

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "==> deleting kind cluster '$CLUSTER_NAME'"
  kind delete cluster --name "$CLUSTER_NAME"
else
  echo "==> no kind cluster named '$CLUSTER_NAME' -- nothing to do"
fi
