# Pet Adoption Platform — Cats vs Dogs MLOps Pipeline

## Assignment Report

| Field | Details |
|---|---|
| **Course** | MLOps (S1-25_AIMLCZG523) |
| **Assignment** | Assignment 2 |
| **Student Name** | Swapnil Jain |
| **Student ID** | 2024ac05788 |
| **Student Email** | 2024ac05788@wilp.bits-pilani.ac.in |
| **GitHub Repository** | [swapniljain782/dogs-cats-adoption](https://github.com/swapniljain782/dogs-cats-adoption.git) |
| **Demo Recording** | [Google Drive Link](https://drive.google.com/drive/folders/15zPHnONEhsidoQ-lxmURWGXy9dmRkI7k?usp=sharing) |

---

## 1. Project Overview

This project implements an end-to-end MLOps pipeline for a **Cats vs Dogs image classifier** designed for a pet adoption platform. The system covers the full machine learning lifecycle: data versioning, model training, experiment tracking, API serving, containerization, CI/CD automation, deployment, and live monitoring.

**Objective:** Build a production-grade ML service that can classify pet images (cats vs dogs) and serve predictions via a REST API, with full DevOps automation.

---

## 2. Architecture

```
Git (code) + DVC (data/model versioning)
        │
        ▼
   train.py  ──► MLflow (params, metrics, confusion matrix, model artifact)
        │
        ▼
   artifacts/model.pt
        │
        ▼
  FastAPI service (api/main.py)  ──►  Dockerfile  ──►  image
        │   ├── /ui/test-console  (upload a photo, see the prediction)
        │   └── /ui/dashboard     (live usage/latency/utilization)
        ▼
GitHub Actions CI  (test → build → push to ghcr.io)
        │
        ▼
Jenkins CD  ──►  GitOps manifest bump  ──►  ArgoCD sync  ──►  Kubernetes
        │
        ▼
Running service ──► logging + /metrics + /dashboard/metrics ──► simulate_traffic.py
```

---

## 3. Technologies Used

| Layer | Technology | Purpose |
|---|---|---|
| **ML Framework** | PyTorch 2.3.1 | CNN model definition and training |
| **Data Versioning** | DVC 3.51.2 | Track dataset and model artifacts |
| **Experiment Tracking** | MLflow 2.14.1 | Log params, metrics, confusion matrix, model |
| **API Framework** | FastAPI 0.111.0 | REST inference service with async support |
| **Monitoring** | Prometheus Client, psutil | Metrics export and host utilization |
| **Containerization** | Docker (multi-arch: amd64/arm64) | Reproducible deployment image |
| **CI** | GitHub Actions | Automated test + build + push to GHCR |
| **CD** | Jenkins + ArgoCD + Kubernetes | GitOps-based continuous deployment |
| **Data Preprocessing** | Pillow, scikit-learn | Image resize, augmentation, train/val/test split |
| **Testing** | pytest 8.2.2 | Unit tests for preprocessing, model, inference |

---

## 4. Dataset

- **Source:** Kaggle "Dogs vs Cats" dataset
- **Classes:** 2 (cats, dogs)
- **Preprocessing:** Images resized to 224×224 RGB, with optional augmentation (random horizontal flip, rotation, color jitter)
- **Split:** 80% train / 10% validation / 10% test (seed=42 for reproducibility)
- **Versioning:** Raw and processed data tracked via DVC (`data/raw.dvc`, `data/processed.dvc`)

---

## 5. Model Architecture

**SimpleCNN** — a lightweight convolutional neural network designed for fast CPU training:

```
Input (3×224×224)
  → Conv Block 1: Conv2d(3→32) + BN + ReLU + MaxPool
  → Conv Block 2: Conv2d(32→64) + BN + ReLU + MaxPool
  → Conv Block 3: Conv2d(64→128) + BN + ReLU + MaxPool
  → Conv Block 4: Conv2d(128→256) + BN + ReLU + MaxPool
  → Adaptive Average Pooling (256×1×1)
  → Flatten + Dropout(0.3)
  → Linear(256→2)
```

**Training Configuration:**
- Optimizer: Adam (lr=1e-3)
- Loss: CrossEntropyLoss
- Epochs: 10 (default)
- Batch size: 32
- Best model saved based on validation accuracy

**Results:**
- Best Validation Accuracy: **87.0%**
- Test Accuracy: **86.97%**

---

## 6. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Liveness/readiness check; returns model load status |
| POST | `/predict` | Accepts image upload, returns label + confidence scores |
| GET | `/metrics` | Prometheus-text format metrics (or JSON fallback) |
| GET | `/dashboard/metrics` | Rich JSON: request count, latency, CPU/RAM, class distribution, rolling history |
| GET | `/ui/test-console/` | Web UI for drag-and-drop image testing |
| GET | `/ui/dashboard/` | Live monitoring dashboard (ECG-style latency, utilization charts) |

**Example Response (`/predict`):**
```json
{
  "label": "cats",
  "probability": 0.9234,
  "probabilities": {"cats": 0.9234, "dogs": 0.0766}
}
```

---

## 7. CI/CD Pipeline

### 7.1 Continuous Integration (GitHub Actions — `ci.yml`)

**Trigger:** Every push to any branch; pull requests to `main`.

| Stage | Action |
|---|---|
| **Test** | Install dependencies (CPU-only PyTorch), run `pytest -v`, upload JUnit XML report |
| **Build & Push** | Create placeholder model if none exists, log in to GHCR, build multi-arch Docker image (amd64 + arm64), push with SHA + `latest` tags |
| **Trigger Jenkins CD** | On merge to `main`, send `IMAGE_TAG=<git-sha>` to Jenkins via parameterized build trigger |

### 7.2 Continuous Deployment (Jenkins + ArgoCD)

**Jenkinsfile pipeline stages:**

1. **Bump image tag** — Runs `kustomize edit set image` to update the deployment manifest with the new image tag, commits the change back to `main`
2. **Sync via ArgoCD** — Triggers ArgoCD to sync the GitOps manifest to the Kubernetes cluster
3. **Smoke test** — Port-forwards to the service, runs health check (with retries), sends a test image to `/predict`, validates response shape
4. **Rollback on failure** — If smoke test fails, Jenkins runs `argocd app rollback` to revert

**Required Jenkins credentials:** `git-push-creds`, `argocd-auth-token`, `pet-classifier-api-key`

### 7.3 Kubernetes Deployment

- Namespace: `pet-adoption`
- HPA: Autoscales 2–6 replicas on CPU/memory
- Services: ClusterIP (internal) and NodePort (for local kind/minikube)
- Ingress: Included but optional (requires ingress controller)

### 7.4 Docker Compose (Alternative)

```bash
cd deployment && docker compose up -d
```

---

## 8. Testing

### Unit Tests

| Test File | Coverage |
|---|---|
| `tests/test_preprocess.py` | Split index proportions, image resizing to 224×224 RGB, missing class error handling |
| `tests/test_inference.py` | Model forward pass output shape, prediction result validity (label, probability, softmax sum), missing checkpoint error |

**Key assertions tested:**
- Split indices produce correct proportions with no overlap
- Preprocessed images are 224×224 RGB
- Model output shape is `(batch, 2)`
- Prediction probabilities sum to 1.0
- Labels are restricted to `cats` or `dogs`

### Post-Deployment Testing

- `scripts/smoke_test.py` — Health check + single prediction call (used in CD pipeline)
- `scripts/simulate_traffic.py` — Batch accuracy evaluation against labeled test set (reports accuracy + average latency)

---

## 9. Monitoring & Observability

| Feature | Implementation |
|---|---|
| **Request logging** | Middleware logs method, path, status, latency (no PII/image bytes) |
| **Prometheus metrics** | `/metrics` endpoint: request count, latency histogram, predictions by class |
| **Dashboard metrics** | `/dashboard/metrics`: request count, error rate, avg latency, uptime, class distribution, total bytes processed, payload throughput (KB/s), host CPU %, host RAM %, rolling 50-request history |
| **Live dashboards** | `/ui/dashboard/` — real-time charts for latency (ECG-style), class distribution, utilization |
| **Post-deploy accuracy** | `simulate_traffic.py` fires labeled test images and reports batch accuracy |

---

## 10. Data & Model Versioning (DVC)

**Pipeline (`dvc.yaml`):**
```
preprocess → train
```

- **Stage 1 — preprocess:** `python src/data/preprocess.py --input data/raw --output data/processed --img-size 224`
  - Deps: `src/data/preprocess.py`, `data/raw`
  - Outs: `data/processed`
- **Stage 2 — train:** `python src/models/train.py --data data/processed --epochs 10`
  - Deps: `src/models/train.py`, `src/models/model.py`, `src/data/dataset.py`, `data/processed`
  - Outs: `artifacts/model.pt`
  - Metrics: `artifacts/metrics.json` (cache: false)

Reproducible via `dvc repro`.

---

## 11. Containerization

**Dockerfile highlights:**
- Base image: `python:3.11-slim`
- Multi-arch support: Conditional pip install (CPU-only torch for amd64, standard PyPI for arm64)
- Health check: Built-in `HEALTHCHECK` using Python urllib
- Bundles: `src/`, `api/`, `ui/`, `artifacts/`
- Exposed port: 8000

```bash
docker build -t pet-classifier:local .
docker run -p 8000:8000 pet-classifier:local
```

---

## 12. Repository Structure

```
pet-adoption-cv/
├── api/
│   ├── main.py                  # FastAPI service (5 endpoints + 2 UI mounts)
│   └── schemas.py               # Pydantic response models
├── artifacts/
│   ├── metrics.json             # Training metrics (best_val_acc: 0.87, test_acc: 0.87)
│   ├── model.pt                 # Trained model checkpoint
│   ├── loss_curve.png           # Training/validation loss curve
│   └── confusion_matrix.png     # Test-set confusion matrix
├── data/
│   ├── raw/                     # Original Kaggle images (DVC-tracked)
│   └── processed/               # 224×224 train/val/test splits (DVC-tracked)
├── deployment/
│   ├── argocd/                  # ArgoCD project + application manifests
│   ├── docker-compose.yml       # Compose-based deployment
│   ├── jenkins/                 # Jenkins agent Dockerfile + RBAC
│   ├── k8s/                     # Kubernetes manifests (namespace, deployment, service, HPA, ingress)
│   └── monitoring/              # Prometheus + Grafana configs
├── src/
│   ├── data/
│   │   ├── dataset.py           # PyTorch Dataset/DataLoader with augmentation
│   │   └── preprocess.py        # Resize, augment, split raw images
│   ├── models/
│   │   ├── model.py             # SimpleCNN (4 conv blocks + GAP + linear head)
│   │   └── train.py             # Training loop + MLflow logging
│   └── utils/
│       └── inference.py         # Model loading + single-image prediction
├── tests/
│   ├── test_preprocess.py       # Preprocessing unit tests
│   └── test_inference.py        # Model + inference unit tests
├── ui/
│   ├── test-console/            # Drag-and-drop image testing UI
│   └── dashboard/               # Live monitoring dashboard UI
├── scripts/
│   ├── simulate_traffic.py      # Post-deploy batch accuracy check
│   └── smoke_test.py            # Health + predict smoke test
├── .github/workflows/
│   ├── ci.yml                   # Test + build + push + trigger Jenkins
│   ├── cd-compose.yml           # Docker Compose deployment path
│   └── cd-k8s.yml               # Kubernetes deployment path
├── Jenkinsfile                  # CD pipeline (GitOps manifest bump → ArgoCD sync → smoke test → rollback)
├── Dockerfile                   # Multi-arch container image
├── dvc.yaml                     # DVC pipeline (preprocess → train)
├── requirements.txt             # Python dependencies
└── README.md                    # Full project documentation
```

---

## 13. Key Design Decisions

1. **Lightweight CNN over transfer learning** — Chose a small custom CNN for fast CPU training and demo simplicity, while still being a real convolutional baseline (not logistic regression on flattened pixels).

2. **DVC for data versioning** — Keeps large datasets out of git while maintaining reproducible pipelines via `dvc repro`.

3. **MLflow for experiment tracking** — Logs all params, metrics, confusion matrices, loss curves, and model artifacts in a single platform.

4. **Dual CD paths** — Docker Compose for simple deployments; Kubernetes with ArgoCD for production-grade GitOps.

5. **Jenkins + ArgoCD separation of concerns** — Jenkins handles the GitOps manifest bump and smoke testing; ArgoCD owns the actual cluster reconciliation (config management).

6. **Multi-arch Docker builds** — Supports both amd64 (CI runners, cloud VMs) and arm64 (Apple Silicon dev machines, kind clusters on M-series Macs).

7. **No PII logging** — Request middleware logs method/path/status/latency only; image bytes are never logged or stored.

---

## 14. How to Run

### Local Development
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Preprocess data
python src/data/preprocess.py --input data/raw --output data/processed --img-size 224

# Train model
python src/models/train.py --data data/processed --epochs 10 --batch-size 32 --lr 1e-3

# Run API
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
pytest -v
```

### Docker
```bash
docker build -t pet-classifier:local .
docker run -p 8000:8000 pet-classifier:local
```

### Kubernetes (local kind)
```bash
./deployment/k8s/local-kind-deploy.sh
```

---

## 15. Model Performance Summary

| Metric | Value |
|---|---|
| Best Validation Accuracy | 87.00% |
| Test Accuracy | 86.97% |
| Model Parameters | ~4 conv blocks (32→64→128→256 channels) |
| Input Size | 224×224 RGB |
| Output | Binary (cats / dogs) with softmax probabilities |

---

## 16. Screenshots

### 16.1 Test Console UI — Model Prediction

Upload a cat image via drag-and-drop. The model correctly classifies it as **CATS — 98%** confidence with a live health indicator showing "Service healthy · model loaded".

![Test Console UI — Cat classified as 98% Cats](screenshots/test-console-cat.png)

### 16.2 Live Monitoring Dashboard

Real-time dashboard showing service vitals: 3 requests served, 545ms average latency, 3m 20s uptime, 0.0% error rate, 26.17 KB/s throughput. Includes latency pulse chart, class distribution donut, CPU (8.3%) and Memory (76.7%) utilization, and payload throughput metrics.

![Live Monitoring Dashboard](screenshots/dashboard-metrics.png)

### 16.3 Prometheus Metrics Endpoint

`/metrics` endpoint exposing Prometheus-text format metrics including `predict_requests_total`, `predict_latency_seconds` histogram, and `predictions_by_class_total` counters — ready for scraping by a Prometheus server.

![Prometheus Metrics Endpoint](screenshots/prometheus-metrics.png)

### 16.4 Health Check Endpoint

`/health` endpoint returning `{"status":"ok","model_loaded":true}` — used for Kubernetes liveness/readiness probes and the CI/CD smoke test.

![Health Check Endpoint](screenshots/health-endpoint.png)

### 16.5 ArgoCD — GitOps Deployment

ArgoCD application `pet-classifier` in the `pet-adoption` project. Status shows **Healthy** with the repository pointing to `swapniljain782/dogs-cats-adoption`, target revision `main`, and last sync 3 minutes ago.

![ArgoCD Application — pet-classifier](screenshots/argocd-application.png)

### 16.6 Jenkins — CD Pipeline

Jenkins dashboard showing the `pet-classifier-cd` pipeline with build #69 succeeding (1 min 56 sec). Build executor currently running build #79 on the "Sync via ArgoCD" stage — demonstrating the automated GitOps deployment flow.

![Jenkins CD Pipeline](screenshots/jenkins-pipeline.png)

---

*Report generated on: August 30, 2026*
