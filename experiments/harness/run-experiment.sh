#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RESULTS_DIR="$REPO_DIR/experiments/results"
VM_IP=$(cd "$REPO_DIR/opentofu/proxmox-vm" && tofu output -raw vm_ip_address)
SSH="ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=10 ubuntu@$VM_IP"
SCP="scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o LogLevel=ERROR"
KCFG="--kubeconfig $REPO_DIR/ansible/kubeconfig"

VARIANT="$1"
SCENARIO="$2"
REP="$3"

RUN_ID="${VARIANT}-${SCENARIO}-rep${REP}"
RUN_DIR="$RESULTS_DIR/$RUN_ID"
mkdir -p "$RUN_DIR"

K6_DURATION=240
case "$SCENARIO" in
  success) K6_DURATION=180 ;;
  faulty) K6_DURATION=240 ;;
esac

log() { echo "[run $RUN_ID $(date +%s)] $*"; }

log "setting up VM result dir"
$SSH "mkdir -p ~/wab-results/$RUN_ID"
$SCP "$REPO_DIR/experiments/harness/load.js" "$REPO_DIR/experiments/harness/sampler.sh" "ubuntu@$VM_IP:~/wab-results/$RUN_ID/"

log "starting k6 load ($K6_DURATION s)"
$SSH "cd ~/wab-results/$RUN_ID && nohup env TARGET_RPS=500 RUN_DURATION=${K6_DURATION}s k6 run --out json=k6.json load.js > k6-stdout.txt 2>&1 & echo \$! > k6.pid"

log "starting pod sampler"
$SSH "cd ~/wab-results/$RUN_ID && nohup bash sampler.sh sampler.csv $((K6_DURATION + 20)) > /dev/null 2>&1 & echo \$! > sampler.pid"

sleep 20
T0=$(date +%s.%N)
log "t0=$T0 flipping manifests to v2"
git -C "$REPO_DIR" checkout -q main

if [ "$SCENARIO" = "success" ]; then
  sed -i 's/newTag: v1/newTag: v2/' "apps/overlays/$VARIANT/kustomization.yaml"
  sed -i '/name: APP_VERSION/{n;s/value: v1/value: v2/}' "apps/overlays/$VARIANT/deployment.yaml" "apps/overlays/$VARIANT/rollout.yaml"
else
  sed -i 's/newTag: v1/newTag: v2/' "apps/overlays/$VARIANT/kustomization.yaml"
  sed -i '/name: APP_VERSION/{n;s/value: v1/value: v2/}' "apps/overlays/$VARIANT/deployment.yaml" "apps/overlays/$VARIANT/rollout.yaml"
  sed -i '/name: APP_FAILURE_MODE/{n;s/value: ""/value: quotes_500/}' "apps/overlays/$VARIANT/deployment.yaml" "apps/overlays/$VARIANT/rollout.yaml"
fi

git -C "$REPO_DIR" add -A
git -C "$REPO_DIR" commit -q -m "experiment: $RUN_ID switch to v2"
git -C "$REPO_DIR" push -q origin main
T_PUSH=$(date +%s.%N)
log "pushed (t_push=$T_PUSH)"

APP="quoter-baseline"
[ "$VARIANT" = "rollout" ] && APP="quoter-rollout"
$SSH "argocd app sync $APP --grpc-web > /dev/null 2>&1" || true
T_SYNC=$(date +%s.%N)
log "sync triggered (t_sync=$T_SYNC)"

if [ "$SCENARIO" = "success" ]; then
  timeout 180 $SSH "argocd app wait $APP --health --timeout 150 --grpc-web > /dev/null 2>&1"
  T_HEALTHY=$(date +%s.%N)
  log "rollout healthy (t_healthy=$T_HEALTHY)"
  sleep 25
  echo "t0=$T0,t_push=$T_PUSH,t_sync=$T_SYNC,t_healthy=$T_HEALTHY" > "$RUN_DIR/timestamps.csv"
else
  log "letting faulty v2 run for 40s"
  sleep 40
  T1=$(date +%s.%N)
  log "t1=$T1 rolling back"
  git -C "$REPO_DIR" revert -q --no-edit HEAD
  git -C "$REPO_DIR" push -q origin main
  T_REVERT=$(date +%s.%N)
  log "revert pushed (t_revert=$T_REVERT)"
  $SSH "argocd app sync $APP --grpc-web > /dev/null 2>&1" || true
  T_SYNC2=$(date +%s.%N)
  log "rollback sync (t_sync2=$T_SYNC2)"
  timeout 240 $SSH "argocd app wait $APP --health --timeout 200 --grpc-web > /dev/null 2>&1"
  T_STABLE=$(date +%s.%N)
  log "stable again (t_stable=$T_STABLE)"
  sleep 25
  echo "t0=$T0,t_push=$T_PUSH,t_sync=$T_SYNC,t_revert=$T_REVERT,t_sync2=$T_SYNC2,t_stable=$T_STABLE" > "$RUN_DIR/timestamps.csv"
fi

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
