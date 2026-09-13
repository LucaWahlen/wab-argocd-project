# WAB Argo CD demonstrator

OpenTofu provisions a Proxmox VM, Ansible bootstraps a kind cluster (podman) with Argo CD and Argo Rollouts, and Argo CD deploys the `shipping-cost-api` demo app.

## Prerequisites

All test paths below need a bootstrapped rig and a deployed app:

```
make bootstrap      # rig (kind, kubectl, argocd, k6) + kind cluster + Argo CD
make build-api      # build image on the VM, load it into kind
make deploy-apps    # register quoter-baseline / quoter-rollout Applications
```

Sync (manual by design): open `https://<vm-ip>:8443` (self-signed, user `admin`, password via `make argocd-password`) and sync `quoter-baseline`, or from the VM:

```
argocd login localhost:8443 --insecure --username admin
argocd app sync quoter-baseline
argocd app wait quoter-baseline --health --timeout 150
```

The VM IP is `cd opentofu/proxmox-vm && tofu output -raw vm_ip_address`.

## Go unit tests

```
cd apps/shipping-cost-api
go test ./...
go vet ./...
```

Coverage: tariff class/price/day rules incl. boundary values, validation errors, `quotes_500` failure mode; HTTP layer: version headers, liveness, readiness with start delay, `unready` failure mode, `SetNotReady` after SIGTERM, JSON/method handling.

## Running the API locally

```
cd apps/shipping-cost-api
go run ./cmd/shipping-cost-api
```

```
curl -s -X POST localhost:8080/v1/quotes \
  -d '{"weightKg":4.5,"lengthCm":40,"widthCm":30,"heightCm":20,"destinationZone":"EU","service":"express"}'
curl -s localhost:8080/health/live
curl -s localhost:8080/health/ready
```

Behavior switches for manual verification:

| Environment variable | Effect |
| --- | --- |
| `APP_START_DELAY_SECONDS=10` | readiness returns 503 for 10s, then 200 |
| `APP_SHUTDOWN_DELAY_SECONDS=10` | on SIGTERM readiness drops immediately, requests keep being served for 10s |
| `APP_FAILURE_MODE=quotes_500` | every quote returns 500 |
| `APP_FAILURE_MODE=unready` | readiness always returns 503 |

## k6 smoke test

`make smoke` copies `experiments/k6/smoke.js` to the VM and runs it there against the NodePort mapping (`localhost:8000` -> node port 30080). It checks for 30s at 1 VU:

- quote responses return 200
- response contains `shippingClass`
- response carries the `X-Application-Version` header

Requires `make build-api` and a synced app first.
