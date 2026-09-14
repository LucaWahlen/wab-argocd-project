#!/bin/bash
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VM_IP=$(cd "$REPO_DIR/opentofu/proxmox-vm" && tofu output -raw vm_ip_address)
SSH="ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=10 ubuntu@$VM_IP"

log() { echo "[campaign $(date +%s)] $*"; }

switch_variant() {
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

log "=== phase 0: prestudy (canary vs blue-green, one run each) ==="
python3 - <<'EOF'
from pathlib import Path
p = Path("apps/overlays/rollout/rollout.yaml")
text = p.read_text()
text = text.replace(
    """  strategy:
    blueGreen:
      activeService: shipping-cost-api
      previewService: shipping-cost-api-preview
      scaleDownDelaySeconds: 10""",
    """  strategy:
    canary:
      steps:
        - setWeight: 50
        - pause:
            duration: 20s""",
)
p.write_text(text)
EOF
git add -A && git commit -q -m "experiment: prestudy canary strategy" && git push -q origin main
switch_variant rollout
bash experiments/harness/run-experiment.sh rollout success pre-canary
git revert --no-edit HEAD && git push -q origin main
switch_variant rollout
bash experiments/harness/run-experiment.sh rollout success pre-bluegreen

log "=== phase 1: measured runs, variant A (rolling update) ==="
switch_variant baseline
for rep in 1 2 3 4 5; do
  bash experiments/harness/run-experiment.sh baseline success "$rep"
done
for rep in 1 2 3 4 5; do
  bash experiments/harness/run-experiment.sh baseline faulty "$rep"
done

log "=== phase 2: measured runs, variant B (argo rollouts blue-green) ==="
switch_variant rollout
for rep in 1 2 3 4 5; do
  bash experiments/harness/run-experiment.sh rollout success "$rep"
done
for rep in 1 2 3 4 5; do
  bash experiments/harness/run-experiment.sh rollout faulty "$rep"
done

log "=== phase 3: restore baseline state ==="
switch_variant baseline
log "campaign complete"
