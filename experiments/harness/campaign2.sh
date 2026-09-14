#!/bin/bash
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VM_IP=$(cd "$REPO_DIR/opentofu/proxmox-vm" && tofu output -raw vm_ip_address)
SSH="ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=10 ubuntu@$VM_IP"

log() { echo "[campaign2 $(date +%s)] $*"; }

source_switch() {
  TARGET="$1"
  case "$TARGET" in
    baseline) OTHER="quoter-rollout" ;;
    rollout) OTHER="quoter-baseline" ;;
  esac
  if $SSH "argocd app list -o name 2>/dev/null | grep -q '/$OTHER$'"; then
    log "deleting $OTHER"
    $SSH "argocd app delete $OTHER --yes --grpc-web" || true
    sleep 5
  fi
  kubectl --kubeconfig "$REPO_DIR/ansible/kubeconfig" apply -f "$REPO_DIR/apps/applications" > /dev/null
  $SSH "argocd app sync $TARGET --grpc-web > /dev/null 2>&1"
  $SSH "argocd app wait $TARGET --health --timeout 300 --grpc-web > /dev/null 2>&1"
  WORKLOADS=$(kubectl --kubeconfig "$REPO_DIR/ansible/kubeconfig" get deployment,rollout -n wab --no-headers 2>/dev/null | awk '{print $1"/"$2}')
  log "variant active: $TARGET (workloads: $WORKLOADS)"
}

cd "$REPO_DIR"

log "=== genuine blue-green prestudy run ==="
source_switch rollout
bash experiments/harness/run-experiment.sh rollout success pre-bluegreen

log "=== phase F: variant A faulty + rollback (rolling update) ==="
source_switch baseline
for rep in 1 2 3 4 5; do
  bash experiments/harness/run-experiment.sh baseline faulty "$rep"
done

log "=== phase G: variant B blue-green, success + faulty ==="
source_switch rollout
for rep in 1 2 3 4 5; do
  bash experiments/harness/run-experiment.sh rollout success "$rep"
done
for rep in 1 2 3 4 5; do
  bash experiments/harness/run-experiment.sh rollout faulty "$rep"
done

log "=== restore baseline variant ==="
source_switch baseline
log "campaign2 complete"
