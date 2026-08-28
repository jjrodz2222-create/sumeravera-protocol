# SumerAvera Protocol — Deployment Guide

## Architecture Overview

```
Internet
   │
   ▼
honeypot-perimeter  (port 3003 / LoadBalancer)  ← edge decoy
   │
   ▼  (threat telemetry → sumera-layer)
avera-engine        (port 3002 / ClusterIP)     ← validation
   │
   ▼
sumera-layer        (port 3001 / ClusterIP)     ← immutable ledger
paws-connect        (port 3004 / ClusterIP)     ← identity nodes
   │
   ▼
prometheus + grafana (monitoring)
```

---

## Local Deployment (Docker Compose)

### Prerequisites
- Docker ≥ 24
- Docker Compose plugin ≥ 2.20

### Steps

```bash
# 1. Clone repo
git clone https://github.com/jjrodz2222-create/sumeravera-protocol
cd sumeravera-protocol

# 2. Create environment file
cp .env.example .env
# Edit .env if needed (ports, Grafana credentials)

# 3. Build & start the full stack
docker compose up --build

# 4. Validate services
curl http://localhost:3001/health        # SumerA Layer
curl http://localhost:3002/health        # Avera Engine
curl http://localhost:3003/health        # Honeypot Perimeter
curl http://localhost:3004/health        # Paws Connect
curl http://localhost:9090/-/healthy     # Prometheus
# Open http://localhost:3000              # Grafana (admin / changeme)

# 5. Verify ledger chain integrity
curl http://localhost:3001/ledger/verify/chain

# 6. Test validation
curl -X POST http://localhost:3002/validate \
  -H 'Content-Type: application/json' \
  -d '{"payload":{"source":"test","timestamp":1234567890,"data":"hello"}}'

# 7. Register a Paws Connect identity node
curl -X POST http://localhost:3004/nodes \
  -H 'Content-Type: application/json' \
  -d '{
    "species_classification": "canine",
    "steward_signature": "sig-abc123",
    "biometric_markers": {"primary_marking_hash": "hash-xyz789"}
  }'
```

---

## Cloud / Production Deployment (Kubernetes)

### Prerequisites
- `kubectl` configured against your cluster
- Container images pushed to a registry (see CI/CD below)

### Steps

```bash
# 1. Apply the full stack manifest
kubectl apply -f k8s/svp-stack.yml

# 2. Watch rollout
kubectl rollout status deployment/sumera-layer -n svp
kubectl rollout status deployment/avera-engine -n svp
kubectl rollout status deployment/honeypot-perimeter -n svp
kubectl rollout status deployment/paws-connect -n svp

# 3. Get the Honeypot external IP (edge load balancer)
kubectl get service honeypot-perimeter -n svp

# 4. Forward ports for internal services (dev/debug only)
kubectl port-forward svc/sumera-layer 3001:3001 -n svp
kubectl port-forward svc/avera-engine 3002:3002 -n svp
```

### Required Secrets
| Secret | Purpose |
|---|---|
| `KUBECONFIG` (base64) | GitHub Actions deploy job |

---

## CI/CD Pipeline

The `.github/workflows/ci-cd.yml` pipeline:

1. **Test** — runs `npm test` for each service on every push/PR
2. **Build** — builds and pushes Docker images to GHCR on `main` merges
3. **Deploy** — applies updated K8s manifests using the SHA-tagged images

Image naming convention: `ghcr.io/<owner>/svp-<service>:sha-<7-char-sha>`

---

## Monitoring

| Endpoint | Service |
|---|---|
| `http://localhost:9090` | Prometheus |
| `http://localhost:3000` | Grafana (admin / changeme) |
| `GET /metrics` on any service | Prometheus scrape target |

Key metrics:
- `sumera_ledger_entries_total` — entries by category
- `avera_validations_total` — accepted vs rejected signals
- `avera_validation_duration_seconds` — validation latency
- `honeypot_threats_total` — threat events by severity
- `honeypot_blocklist_size` — dynamic blocklist size
- `paws_nodes_registered_total` — identity nodes by species
- `paws_verifications_total` — verification outcomes

---

## Firewall Auto-Update Pattern

The Honeypot auto-promotes `critical` severity probes to the in-memory blocklist.
To propagate that blocklist to your network edge firewall:

```bash
# Pull current blocklist from the Honeypot
curl http://<honeypot>:3003/blocklist

# Feed IPs into your firewall (example: iptables)
curl -s http://<honeypot>:3003/blocklist | \
  jq -r '.ips[]' | \
  xargs -I{} iptables -A INPUT -s {} -j DROP
```

In production, script this as a cron job or wire it to a webhook triggered by the Prometheus `honeypot_threats_total{severity="critical"}` alert.
