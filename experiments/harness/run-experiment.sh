#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RESULTS_DIR="$REPO_DIR/experiments/results"
VM_IP=$(cd "$REPO_DIR/opentofu/proxmox-vm" && tofu output -raw vm_ip_address)
SSH="ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=10 ubuntu@$VM_IP"
SCP="scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o LogLevel=ERROR"
KUBECTL="kubectl --kubeconfig $REPO_DIR/ansible/kubeconfig"

VARIANT="$1"
SCENARIO="$2"
REP="$3"

RUN_ID="${VARIANT}-${SCENARIO}-rep${REP}"
RUN_DIR="$RESULTS_DIR/$RUN_ID"
mkdir -p "$RUN_DIR"

K6_DURATION=180
if [ "$SCENARIO" = "faulty" ]; then
  K6_DURATION=240
fi

WORKLOAD="deployment.yaml"
[ "$VARIANT" = "rollout" ] && WORKLOAD="rollout.yaml"
APP="quoter-baseline"
[ "$VARIANT" = "rollout" ] && APP="quoter-rollout"

log() { echo "[run $RUN_ID $(date +%s)] $*"; }

cluster_images() {
  $KUBECTL get pods -n wab -o json 2>/dev/null | python3 -c '
import json, sys
d = json.load(sys.stdin)
items = d.get("items", [])
if not items:
    print("none")
else:
    print(",".join(sorted(set(p["spec"]["containers"][0]["image"].rsplit(":", 1)[-1] for p in items))))
'
}

wait_images() {
  local want="$1" timeout_s="$2" start cur
  start=$(date +%s)
  while true; do
    cur=$(cluster_images)
    if [ "$cur" = "$want" ]; then
      return 0
    fi
    if [ $(( $(date +%s) - start )) -gt "$timeout_s" ]; then
      log "TIMEOUT waiting for images=$want (last: $cur)"
      return 1
    fi
    sleep 3
  done
}

log "normalizing repo and cluster to v1"
git -C "$REPO_DIR" checkout -q main
sed -i 's/newTag: v2/newTag: v1/' "apps/overlays/$VARIANT/kustomization.yaml"
sed -i '/name: APP_VERSION/{n;s/value: v2/value: v1/;}' "apps/overlays/$VARIANT/$WORKLOAD"
sed -i '/name: APP_FAILURE_MODE/{n;s/value: quotes_500/value: ""/;}' "apps/overlays/$VARIANT/$WORKLOAD"
git -C "$REPO_DIR" add -A
if ! git -C "$REPO_DIR" diff --cached --quiet; then
  git -C "$REPO_DIR" commit -q -m "experiment: reset to v1 before $RUN_ID"
  git -C "$REPO_DIR" push -q origin main
fi
$SSH "argocd app sync $APP --grpc-web > /dev/null 2>&1" || true
wait_images v1 300
$SSH "argocd app wait $APP --health --timeout 300 --grpc-web > /dev/null 2>&1"
log "cluster at v1, healthy"

$SSH "rm -rf ~/wab-results/$RUN_ID && mkdir -p ~/wab-results/$RUN_ID"
$SCP "$REPO_DIR/experiments/harness/load.js" "$REPO_DIR/experiments/harness/sampler.sh" "ubuntu@$VM_IP:~/wab-results/$RUN_ID/"

log "starting k6 load ($K6_DURATION s)"
$SSH "cd ~/wab-results/$RUN_ID; nohup env TARGET_RPS=500 RUN_DURATION=${K6_DURATION}s k6 run --out json=k6.json load.js > k6-stdout.txt 2>&1 < /dev/null & echo \$! > k6.pid"
log "starting pod sampler"
$SSH "cd ~/wab-results/$RUN_ID; nohup bash sampler.sh sampler.csv $((K6_DURATION + 30)) > /dev/null 2>&1 < /dev/null & echo \$! > sampler.pid"

sleep 20
T0=$(date +%s.%N)
log "t0=$T0 flipping manifests to v2"

sed -i 's/newTag: v1/newTag: v2/' "apps/overlays/$VARIANT/kustomization.yaml"
sed -i '/name: APP_VERSION/{n;s/value: v1/value: v2/;}' "apps/overlays/$VARIANT/$WORKLOAD"
if [ "$SCENARIO" = "faulty" ]; then
  sed -i '/name: APP_FAILURE_MODE/{n;s/value: ""/value: quotes_500/;}' "apps/overlays/$VARIANT/$WORKLOAD"
fi

git -C "$REPO_DIR" add -A
if git -C "$REPO_DIR" diff --cached --quiet; then
  log "FATAL: flip produced no manifest change"
  exit 1
fi
git -C "$REPO_DIR" commit -q -m "experiment: $RUN_ID switch to v2"
git -C "$REPO_DIR" push -q origin main
T_PUSH=$(date +%s.%N)
log "pushed (t_push=$T_PUSH)"

$SSH "argocd app sync $APP --grpc-web > /dev/null 2>&1" || true
T_SYNC=$(date +%s.%N)
log "sync triggered (t_sync=$T_SYNC)"

if [ "$SCENARIO" = "success" ]; then
  wait_images v2 300
  $SSH "argocd app wait $APP --health --timeout 300 --grpc-web > /dev/null 2>&1"
  T_HEALTHY=$(date +%s.%N)
  log "rollout healthy (t_healthy=$T_HEALTHY)"
  echo "t0=$T0,t_push=$T_PUSH,t_sync=$T_SYNC,t_healthy=$T_HEALTHY" > "$RUN_DIR/timestamps.csv"
else
  log "letting faulty v2 run for 40s"
  sleep 40
  git -C "$REPO_DIR" revert -q --no-edit HEAD
  git -C "$REPO_DIR" push -q origin main
  T_REVERT=$(date +%s.%N)
  log "revert pushed (t_revert=$T_REVERT)"
  $SSH "argocd app sync $APP --grpc-web > /dev/null 2>&1" || true
  T_SYNC2=$(date +%s.%N)
  log "rollback sync (t_sync2=$T_SYNC2)"
  wait_images v1 300
  $SSH "argocd app wait $APP --health --timeout 300 --grpc-web > /dev/null 2>&1"
  T_STABLE=$(date +%s.%N)
  log "stable again (t_stable=$T_STABLE)"
  echo "t0=$T0,t_push=$T_PUSH,t_sync=$T_SYNC,t_revert=$T_REVERT,t_sync2=$T_SYNC2,t_stable=$T_STABLE" > "$RUN_DIR/timestamps.csv"
fi

sleep 20
log "waiting for k6 to finish"
while $SSH "test -f ~/wab-results/$RUN_ID/k6.pid && kill -0 \$(cat ~/wab-results/$RUN_ID/k6.pid) 2>/dev/null"; do
  sleep 10
done

log "fetching results"
$SCP "ubuntu@$VM_IP:~/wab-results/$RUN_ID/k6.json" "$RUN_DIR/k6.json"
$SCP "ubuntu@$VM_IP:~/wab-results/$RUN_ID/k6-stdout.txt" "$RUN_DIR/k6-stdout.txt"
$SCP "ubuntu@$VM_IP:~/wab-results/$RUN_ID/sampler.csv" "$RUN_DIR/sampler.csv"
$SSH "rm -rf ~/wab-results/$RUN_ID"

python3 "$REPO_DIR/experiments/harness/postprocess.py" "$RUN_DIR"
log "done: $RUN_DIR/summary.json"
