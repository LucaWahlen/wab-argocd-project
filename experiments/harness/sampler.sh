#!/bin/bash
set -u
OUT="$1"
DURATION="$2"
END=$(( $(date +%s) + DURATION ))
echo "epoch,pods,ready,images" > "$OUT"
while [ "$(date +%s)" -lt "$END" ]; do
  TS=$(date +%s.%N)
  LINE=$(sudo kubectl get pods -n wab -o json 2>/dev/null | python3 -c '
import json, sys
d = json.load(sys.stdin)
items = d.get("items", [])
ready = sum(1 for p in items if all(c.get("ready", False) for c in p.get("status", {}).get("containerStatuses", [])))
images = ",".join(sorted(set(p["spec"]["containers"][0]["image"].split(":")[-1] for p in items)))
print(f"{len(items)},{ready},{images}")
' 2>/dev/null || echo "0,0,")
  echo "$TS,$LINE" >> "$OUT"
  sleep 1
done
