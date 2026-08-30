# Pet Adoption Platform — Cats vs Dogs MLOps Pipeline

End-to-end MLOps platform: data versioning, model training, experiment tracking, containerization, CI/CD via GitOps, monitoring, and multiple deployment paths — all on Kubernetes.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DEVELOPER WORKFLOW                                 │
│                                                                             │
│  git push ──► GitHub Actions CI ──► Jenkins CD ──► ArgoCD ──► Kubernetes    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA & TRAINING PIPELINE                           │
│                                                                             │
│  Kaggle Dataset (cats/dogs)                                                │
│       │                                                                     │
│       ▼                                                                     │
│  DVC ─────► preprocess.py ──► data/processed/ (224x224 splits)             │
│       │                                                                     │
│       ▼                                                                     │
│  DVC ─────► train.py ──────► artifacts/model.pt                            │
│       │         │                                                           │
│       │         └──► MLflow (params, metrics, confusion matrix, artifacts)  │
│       │                                                                     │
│       ▼                                                                     │
│  Docker build ──► ghcr.io/.../pet-classifier:<sha>                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        CI/CD PIPELINE (GitOps)                              │
│                                                                             │
│  GitHub Actions CI                                                         │
│  ┌──────────┐  ┌──────────────────┐  ┌─────────────────────────┐          │
│  │ pytest   │→ │ docker build     │→ │ trigger Jenkins CD      │          │
│  │ tests    │  │ push to ghcr.io  │  │ (POST /buildWithParams) │          │
│  └──────────┘  └──────────────────┘  └────────────┬────────────┘          │
│                                                     │                       │
│                                                     ▼                       │
│  Jenkins CD Pipeline (in-cluster)                                         │
│  ┌──────────────────┐  ┌─────────────────────┐  ┌────────────────┐        │
│  │ kustomize edit   │→ │ git push to main    │→ │ argocd sync    │        │
│  │ set image :<sha> │  │ (bump image tag)    │  │ + wait health  │        │
│  └──────────────────┘  └─────────────────────┘  └───────┬────────┘        │
│                                                           │                 │
│                                                           ▼                 │
│  ArgoCD (GitOps)                                                           │
│  ┌────────────────────────────────────────────────────────────────┐        │
│  │ Watches repo ──► detects kustomization.yaml change            │        │
│  │ ──► kubectl apply ──► pet-adoption namespace                  │        │
│  │ Auto-sync + self-heal + prune                                  │        │
│  └────────────────────────────────────────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                       RUNNING PLATFORM (Kubernetes)                         │
│                                                                             │
│  ┌─────────────────── namespace: pet-adoption ───────────────────────┐     │
│  │                                                                     │     │
│  │  ┌─────────────┐    ┌──────────────┐    ┌───────────────────┐    │     │
│  │  │ pet-classify│◄───│ pet-classify │    │ MLflow Server     │    │     │
│  │  │ Deployment  │    │ Service      │    │ (experiment UI)   │    │     │
│  │  │ (2 replicas)│    │ (ClusterIP)  │    │ port 5000         │    │     │
│  │  │ port 8000   │    │ port 80      │    └─────────┬─────────┘    │     │
│  │  └──────┬──────┘    └──────────────┘              │               │     │
│  │         │                                          │               │     │
│  │         ├── /health ──────────────────────┐       │               │     │
│  │         ├── /predict ─────────────────────┤       │               │     │
│  │         ├── /metrics ─────────────────────┤       │               │     │
│  │         ├── /dashboard/metrics ───────────┤       │               │     │
│  │         ├── /ui/test-console/ ────────────┤       │               │     │
│  │         └── /ui/dashboard/ ───────────────┤       │               │     │
│  │                                           │       │               │     │
│  │  ┌──────────────────┐  ┌──────────────┐  │  ┌────┴────┐  ┌──────┤     │
│  │  │ ServiceMonitor   │  │ Prometheus   │  │  │PostgreSQL│  │MinIO │     │
│  │  │ + PrometheusRule │  │ (scrapes /  │  │  │ (backend)│  │ (S3) │     │
│  │  │                  │  │  metrics)    │  │  │ port 5432│  │ 9000 │     │
│  │  └──────────────────┘  └──────┬───────┘  │  └─────────┘  └──────┘     │
│  │                                │          │                             │
│  │                                ▼          │                             │
│  │  ┌──────────────────────────────────┐     │                             │
│  │  │ Grafana                          │     │                             │
│  │  │ (6-panel dashboard, auto-setup)  │     │                             │
│  │  │ port 3000                        │     │                             │
│  │  └──────────────────────────────────┘     │                             │
│  │                                           │                             │
│  └───────────────────────────────────────────┘                             │
│                                                                             │
│  ┌─────────────────── namespace: jenkins ───────────────────────────┐      │
│  │  Jenkins Controller (in-cluster, port 8080)                      │      │
│  │  Runs CD pipeline stages: bump manifest → argocd sync → smoke   │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
│  ┌─────────────────── namespace: argocd ────────────────────────────┐      │
│  │  ArgoCD Server + Application Controller + Redis + Repo Server   │      │
│  │  Watches main branch, auto-syncs to pet-adoption namespace      │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Services & Ports

### Application Services

| Service | Namespace | Port | Type | Description |
|---------|-----------|------|------|-------------|
| pet-classifier | pet-adoption | 8000 | ClusterIP | FastAPI inference API (Cats vs Dogs classifier) |
| pet-classifier-svc | pet-adoption | 80→8000 | ClusterIP | K8s service for the classifier |
| mlflow-server | pet-adoption | 5000 | ClusterIP | MLflow experiment tracking UI + API |
| mlflow-postgres | pet-adoption | 5432 | ClusterIP | PostgreSQL backend for MLflow metadata |
| mlflow-minio | pet-adoption | 9000/9001 | ClusterIP | MinIO object store (S3 API / Console UI) |

### Infrastructure Services

| Service | Namespace | Port | Type | Description |
|---------|-----------|------|------|-------------|
| jenkins | jenkins | 8080 | ClusterIP | Jenkins CI/CD controller |
| argocd-server | argocd | 443 | ClusterIP | ArgoCD GitOps server |
| argocd-server-nodeport | argocd | 30443 | NodePort | ArgoCD UI (local dev access) |

### Monitoring Services

| Service | Namespace | Port | Type | Description |
|---------|-----------|------|------|-------------|
| prometheus-kube-prometheus-prometheus | monitoring | 9090 | ClusterIP | Prometheus metrics server |
| prometheus-grafana | monitoring | 3000 | ClusterIP | Grafana dashboards (admin/admin) |
| prometheus-kube-prometheus-alertmanager | monitoring | 9093 | ClusterIP | Alertmanager for alert routing |

---

## Web UIs

| UI | URL | Description |
|----|-----|-------------|
| Test Console | `http://localhost:8000/ui/test-console/` | Upload an image, see the prediction with confidence |
| Live Dashboard | `http://localhost:8000/ui/dashboard/` | Real-time request count, latency, throughput, utilization |
| MLflow | `http://localhost:5000` | Experiment tracking, run comparison, model registry |
| MinIO Console | `http://localhost:9001` | Object browser for MLflow artifacts |
| Grafana | `http://localhost:3000` | Prometheus dashboards (6 panels for pet-classifier) |
| Prometheus | `http://localhost:9090` | Metrics exploration, alert rules, targets |
| ArgoCD | `https://localhost:30443` | GitOps app status, sync history, rollback |
| Jenkins | `http://localhost:8080` (port-forward) | CD pipeline status, build logs |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Redirects to test console UI |
| GET | `/health` | Health check — returns `{"status": "ok", "model_loaded": true}` |
| POST | `/predict` | Classify an image — multipart/form-data, returns `{label, probability, probabilities}` |
| GET | `/metrics` | Prometheus-format metrics (request count, latency histogram, class distribution) |
| GET | `/dashboard/metrics` | Rich JSON for the live dashboard (requests, latency, throughput, CPU/RAM, last 50 requests) |
| GET | `/ui/test-console/` | Model testing web UI |
| GET | `/ui/dashboard/` | Live monitoring web UI |

---

## Repo Layout

```
├── api/
│   ├── main.py                          # FastAPI app: /health, /predict, /metrics, /dashboard/metrics
│   └── schemas.py                       # Pydantic response models
├── src/
│   ├── data/
│   │   ├── preprocess.py                # Resize → 224x224, augment, split 80/10/10
│   │   └── dataset.py                   # PyTorch Dataset/DataLoader
│   ├── models/
│   │   ├── model.py                     # CNN architecture
│   │   └── train.py                     # Training loop + MLflow logging
│   └── utils/
│       └── inference.py                 # Load model + predict(image)
├── ui/
│   ├── test-console/index.html          # Drag-drop image classification UI
│   └── dashboard/index.html             # Live metrics/latency/utilization UI
├── tests/                               # Pytest unit tests
├── scripts/
│   ├── smoke_test.py                    # Post-deploy health + prediction check (used by CI/CD)
│   ├── simulate_traffic.py              # Batch traffic simulation + accuracy report
│   └── track_performance.py             # Drift detection with accuracy/F1/latency metrics
├── deployment/
│   ├── docker-compose.yml               # Single-service Docker Compose for local dev
│   ├── argocd/
│   │   ├── application.yaml             # ArgoCD Application (pet-classifier)
│   │   ├── project.yaml                 # ArgoCD AppProject (pet-adoption)
│   │   └── install-argocd.sh            # ArgoCD installation script
│   ├── jenkins/
│   │   └── Dockerfile                   # Jenkins image with kubectl/kustomize/argocd
│   ├── k8s/
│   │   ├── kustomization.yaml           # Aggregates all K8s manifests
│   │   ├── namespace.yaml               # pet-adoption namespace
│   │   ├── deployment.yaml              # pet-classifier Deployment (2 replicas, security-hardened)
│   │   ├── service.yaml                 # ClusterIP Service (80 → 8000)
│   │   ├── hpa.yaml                     # HorizontalPodAutoscaler (2-6 replicas)
│   │   ├── pdb.yaml                     # PodDisruptionBudget (minAvailable: 1)
│   │   ├── networkpolicy.yaml           # Ingress/egress restrictions
│   │   ├── servicemonitor.yaml          # ServiceMonitor + 3 PrometheusRule alerts
│   │   ├── grafana-dashboard.yaml       # Grafana dashboard ConfigMap (6 panels)
│   │   ├── mlflow-secrets.yaml          # MLflow PostgreSQL + MinIO passwords
│   │   ├── mlflow-postgres.yaml         # PostgreSQL: PVC + Deployment + Service
│   │   ├── mlflow-minio.yaml            # MinIO: PVC + Deployment + Service
│   │   ├── mlflow-server.yaml           # MLflow tracking server Deployment + Service
│   │   ├── jenkins.yaml                 # Jenkins: PVC + Deployment + Service
│   │   ├── jenkins-rbac.yaml            # Jenkins RBAC (SA + cross-namespace Role)
│   │   └── Jenkinsfile                  # Jenkins CD pipeline definition
│   └── monitoring/
│       ├── docker-compose.yml           # Prometheus + Grafana + Node Exporter (local)
│       ├── prometheus.yml               # Prometheus scrape config
│       └── grafana/                     # Provisioned datasources + dashboards
├── .github/workflows/
│   ├── ci.yml                           # CI: pytest → docker build → push → trigger Jenkins
│   ├── cd-compose.yml                   # CD path A: docker compose (alternative)
│   └── cd-k8s.yml                       # CD path B: kubectl apply (alternative)
├── Jenkinsfile                          # CD path C (primary): Jenkins → ArgoCD GitOps
├── Dockerfile                           # pet-classifier image (python:3.11-slim)
├── dvc.yaml                             # DVC pipeline: preprocess → train
├── requirements.txt                     # Python dependencies
└── .env.local                           # Local environment variables
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker
- kind (or any Kubernetes cluster)
- kubectl, kustomize

### 1. Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

git init && dvc init
dvc remote add -d localstorage /tmp/dvc-storage
```

### 2. Data

Download the Kaggle "Dogs vs Cats" dataset and place images under:

```
data/raw/cats/*.jpg
data/raw/dogs/*.jpg
```

### 3. Preprocess + Train

```bash
# Option A: DVC pipeline
dvc repro

# Option B: Step by step
python src/data/preprocess.py --input data/raw --output data/processed --img-size 224
python src/models/train.py --data data/processed --epochs 10 --batch-size 32 --lr 1e-3
```

Training logs params, metrics, and confusion matrix to MLflow, writes model to `artifacts/model.pt`.

### 4. Run Locally

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
# Open http://localhost:8000/ui/test-console/
```

### 5. Run Tests

```bash
pytest -v
```

---

## Deployment

### Option A: Docker Compose (simplest)

```bash
cd deployment
docker compose up -d
curl http://localhost:8000/health
```

### Option B: Kubernetes with kind (local dev)

```bash
./deployment/k8s/local-kind-deploy.sh
curl http://localhost:30080/health
open http://localhost:30080/ui/test-console/
```

### Option C: Full GitOps with ArgoCD (production)

```bash
# 1. Install ArgoCD
./deployment/argocd/install-argocd.sh

# 2. Install Metrics Server (for HPA)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# 3. Apply monitoring + MLflow stack
kubectl apply -k deployment/k8s/

# 4. Access services via port-forward
kubectl port-forward -n pet-adoption svc/pet-classifier-svc 8000:80
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
kubectl port-forward -n argocd svc/argocd-server 8080:443
```

---

## CI/CD Pipeline

### Primary Flow: GitHub Actions → Jenkins → ArgoCD

```
┌──────────────────────────────────────────────────────────────────┐
│                    GitHub Actions CI                             │
│                                                                  │
│  push/PR ──► pytest ──► docker build ──► push to ghcr.io        │
│              tests      (multi-arch)     :<git-sha> + :latest    │
│                                  │                               │
│                                  ▼                               │
│              trigger Jenkins CD (POST /buildWithParameters)      │
└──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Jenkins CD Pipeline                           │
│                                                                  │
│  kustomize edit set image ──► git push ──► argocd sync          │
│  (bump image tag)            (to main)    (apply to cluster)    │
│                                                                  │
│  smoke test: port-forward ──► curl /health ──► curl /predict    │
│                                                                  │
│  on failure: argocd rollback                                     │
└──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                    ArgoCD (GitOps)                               │
│                                                                  │
│  watches main branch ──► detects kustomization.yaml change      │
│  ──► kubectl apply ──► pet-adoption namespace                   │
│  auto-sync + self-heal + prune                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Jenkins Credentials

| Credential ID | Type | Purpose |
|---------------|------|---------|
| `git-push-creds` | SSH key | Push kustomization.yaml changes to main |
| `argocd-auth-token` | Secret text | ArgoCD API token for ci-deployer role |
| `pet-classifier-api-key` | Secret text | API key for smoke test (optional) |

---

## Monitoring

### Metrics Endpoints

| Endpoint | Format | Content |
|----------|--------|---------|
| `/metrics` | Prometheus text | `predict_requests_total`, `predict_latency_seconds`, `predictions_by_class_total` |
| `/dashboard/metrics` | JSON | Request count, error rate, latency, uptime, class distribution, CPU/RAM, last 50 requests |

### Prometheus Alerts

| Alert | Condition | Severity |
|-------|-----------|----------|
| PetClassifierHighErrorRate | Error rate > 5% for 2 min | Warning |
| PetClassifierHighLatency | P95 latency > 1s for 5 min | Warning |
| PetClassifierDown | Service unreachable for 1 min | Critical |

### Grafana Dashboard Panels

1. Predictions by Class (rate/sec)
2. Latency P50/P95 (ms)
3. Service Status (up/down)
4. Request Rate + Error Rate
5. Memory Usage (bytes)
6. CPU Usage (cores)

---

## Monitoring Setup

### Kubernetes (production)

```bash
# Install kube-prometheus-stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --set grafana.enabled=true \
  --set grafana.sidecar.dashboards.enabled=true \
  --set grafana.sidecar.dashboards.label=grafana_dashboard

# Access
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
```

### Local Docker Compose (development)

```bash
cd deployment/monitoring
docker compose up -d
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000 (admin/admin)
```

---

## Scripts

| Script | Usage | Description |
|--------|-------|-------------|
| `scripts/smoke_test.py` | `python scripts/smoke_test.py --host localhost --port 8000` | Health + prediction check (used by CI/CD) |
| `scripts/simulate_traffic.py` | `python scripts/simulate_traffic.py --url http://localhost:8000 --data-dir data/processed/test --n 30` | Batch accuracy report against live service |
| `scripts/track_performance.py` | `python scripts/track_performance.py --url http://localhost:8091 --samples 50` | Drift detection: accuracy/F1/confusion matrix/latency |
| `deployment/k8s/local-kind-deploy.sh` | `./deployment/k8s/local-kind-deploy.sh` | One-shot local kind cluster setup + deploy |
| `deployment/argocd/install-argocd.sh` | `./deployment/argocd/install-argocd.sh` | Install ArgoCD + register app/project |

---

## Demo Recording Checklist

1. `git push` → show GitHub Actions CI (tests pass, image builds, pushes to ghcr.io)
2. Show Jenkins CD run (bumps manifest, triggers ArgoCD sync)
3. Show ArgoCD dashboard (pet-classifier synced + healthy)
4. Open `/ui/test-console/` → drag in a photo → show prediction
5. Open `/ui/dashboard/` → fire more predictions → watch live charts update
6. Show Grafana dashboard (Prometheus metrics flowing)
7. Show MLflow UI (logged run with params/metrics/confusion matrix)
8. Run `simulate_traffic.py` against live deployment → show batch accuracy
