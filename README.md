## Pet Adoption Platform — Cats vs Dogs MLOps Pipeline

End-to-end MLOps pipeline: data/model versioning → experiment tracking → packaging →
containerization → CI → CD → deployment → monitoring, plus two web UIs (a model
testing console and a live metrics dashboard).

## Architecture

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
GitHub Actions CD  ── pick one ──┬── cd-compose.yml (docker compose up → smoke test)
                                 └── cd-k8s.yml (kustomize → kubectl apply → smoke test)
        │
        ▼
Running service ──► logging + /metrics + /dashboard/metrics ──► simulate_traffic.py
```

## Repo layout

```
data/raw/{cats,dogs}         # put the Kaggle Cats-vs-Dogs images here (DVC-tracked)
data/processed/              # train/val/test splits after preprocess.py (DVC-tracked)
src/data/preprocess.py       # resize -> 224x224 RGB, augment, split 80/10/10
src/data/dataset.py          # PyTorch Dataset/DataLoader
src/models/model.py          # simple CNN
src/models/train.py          # training loop + MLflow logging
src/utils/inference.py       # load model + predict(image)
api/main.py                  # FastAPI: /health, /predict, /metrics, /dashboard/metrics
api/schemas.py                # pydantic response models
ui/test-console/index.html    # model testing UI (upload/drag-drop an image)
ui/dashboard/index.html       # live monitoring UI (usage, latency, utilization)
tests/                        # pytest unit tests
Dockerfile                    # containerize the inference API (bundles ui/ too)
deployment/docker-compose.yml
deployment/k8s/                # Kubernetes option (kustomize-based)
  namespace.yaml
  deployment.yaml
  service.yaml                 # ClusterIP, for use behind an ingress or port-forward
  service-nodeport.yaml        # NodePort variant for quick local kind/minikube access
  hpa.yaml                      # autoscaling on CPU/memory
  ingress.yaml                  # optional, needs an ingress controller
  servicemonitor.yaml          # Prometheus ServiceMonitor + alert rules
  grafana-dashboard.yaml       # Grafana dashboard ConfigMap
  kustomization.yaml
  kind-config.yaml              # local kind cluster config (exposes NodePort 30080)
  local-kind-deploy.sh          # one-shot local k8s deploy for demos
deployment/monitoring/          # Local Prometheus + Grafana stack (docker-compose)
  docker-compose.yml
  prometheus.yml
  grafana/
.github/workflows/ci.yml        # test + build + push image
.github/workflows/cd-compose.yml  # deploy path A: Docker Compose
.github/workflows/cd-k8s.yml      # deploy path B: Kubernetes
scripts/simulate_traffic.py       # post-deploy accuracy/latency batch check
scripts/track_performance.py      # post-deployment performance tracking (M5)
scripts/smoke_test.py             # standalone health+predict smoke test
dvc.yaml                          # DVC pipeline (preprocess -> train)
```

## 1. Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

git init
dvc init
dvc remote add -d localstorage /tmp/dvc-storage   # swap for S3/GCS in real deployments
```

Download the Kaggle "Dogs vs Cats" dataset and place raw images under:

```
data/raw/cats/*.jpg
data/raw/dogs/*.jpg
```

Then version the raw data:

```bash
dvc add data/raw
git add data/raw.dvc .gitignore
git commit -m "Track raw dataset with DVC"
<img width="1295" height="170" alt="image" src="https://github.com/user-attachments/assets/42cb529e-f2bc-49fe-a3a5-1f99c372ce22" />

```

## 2. Preprocess + split

```bash
python src/data/preprocess.py --input data/raw --output data/processed \
    --img-size 224 --train-split 0.8 --val-split 0.1 --test-split 0.1

dvc add data/processed
git add data/processed.dvc
git commit -m "Add processed 224x224 train/val/test splits"
```

Or run the whole DVC pipeline (preprocess -> train) in one shot: `dvc repro`

## 3. Train + track experiments

```bash
mlflow ui --backend-store-uri ./mlruns   # separate terminal, view at localhost:5000
python src/models/train.py --data data/processed --epochs 10 --batch-size 32 --lr 1e-3
```

This logs params/metrics/confusion-matrix/loss-curve to MLflow and writes the final
model to `artifacts/model.pt` (what the API loads).

## 4. Run the API + UIs locally

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

- `http://localhost:8000/` redirects to the testing console
- `http://localhost:8000/ui/test-console/` — drag/drop or click to upload a photo,
  see the predicted label stamped with its confidence, plus a live health indicator
- `http://localhost:8000/ui/dashboard/` — live usage and utilization: request count,
  average latency (as a live ECG-style line), error rate, uptime, class distribution,
  host CPU/RAM, and payload throughput (KB/s — the image-model analog of "token
  throughput" on an LLM dashboard, since there's no token count for an image classifier)
- `curl localhost:8000/health` / `curl -F "file=@some_cat.jpg" localhost:8000/predict`
  still work exactly as before — the UIs just call the same endpoints from the browser

## 5. Containerize

```bash
docker build -t pet-classifier:local .
docker run -p 8000:8000 pet-classifier:local
curl -F "file=@some_cat.jpg" localhost:8000/predict
```

## 6. Tests

```bash
pytest -v
```

## 7. CI

`.github/workflows/ci.yml` runs on every push/PR: checkout, install deps, run `pytest`,
build the Docker image, push to `ghcr.io/<owner>/<repo>/pet-classifier` tagged with the
git SHA and `latest` (main branch only). No extra secrets needed beyond the default
`GITHUB_TOKEN`.

## 8. CD — pick one deployment path

### Option A: Docker Compose

```bash
cd deployment
docker compose up -d
python ../scripts/smoke_test.py --host localhost --port 8000
```

`.github/workflows/cd-compose.yml` runs this same flow on a self-hosted runner after
CI succeeds on `main`, then rolls the job back to a failing state if the smoke test
fails (see the note in the workflow about self-hosted runners vs. SSH-to-a-VM).

### Option B: Kubernetes

Local demo with `kind` (no registry needed):

```bash
./deployment/k8s/local-kind-deploy.sh
curl http://localhost:30080/health
open http://localhost:30080/ui/test-console/
open http://localhost:30080/ui/dashboard/
```

Or apply manually to any cluster:

```bash
cd deployment/k8s
kustomize edit set image ghcr.io/OWNER/REPO/pet-classifier=<your-image>:<tag>
kustomize build . | kubectl apply -f -
kubectl rollout status deployment/pet-classifier -n pet-adoption
kubectl port-forward -n pet-adoption svc/pet-classifier-svc 8000:80
```
<img width="1470" height="590" alt="image" src="https://github.com/user-attachments/assets/6b9eed5b-5e14-4706-8763-7725fa8c9615" />
<img width="1470" height="716" alt="image" src="https://github.com/user-attachments/assets/cd4a78bf-8253-4092-b007-3f41584b08a9" />
<img width="1470" height="150" alt="image" src="https://github.com/user-attachments/assets/769f382d-2da3-48d6-acb4-5a2312b20db2" />
<img width="1470" height="879" alt="image" src="https://github.com/user-attachments/assets/7b16a5d6-e7a8-4d19-8d17-1b675b8dcb2d" />
<img width="1470" height="881" alt="image" src="https://github.com/user-attachments/assets/6bf0f110-e05a-4741-9ac7-57944a4efdc1" />
<img width="1470" height="487" alt="image" src="https://github.com/user-attachments/assets/7de53305-db14-41ed-a51c-87eda3b1b122" />



`.github/workflows/cd-k8s.yml` does the same in CI: sets the image via kustomize,
applies manifests, waits for rollout, smoke-tests via `kubectl port-forward`, and
**automatically rolls back** (`kubectl rollout undo`) if the smoke test fails. It
needs one repo secret, `KUBE_CONFIG` (base64-encoded kubeconfig for a reachable
cluster):

```bash
cat ~/.kube/config | base64 -w0
```

`hpa.yaml` autoscales 2–6 replicas on CPU/memory; `ingress.yaml` is included but
commented out of `kustomization.yaml` since it needs an ingress controller — uncomment
it if your cluster has one (e.g. ingress-nginx on kind/minikube).

**Enable only one of `cd-compose.yml` / `cd-k8s.yml`** (disable the other in your
repo's Actions settings) so they don't race to redeploy the same image differently.

## 9. Monitoring

- Every request/response is logged (method, path, status, latency; no image bytes/PII).
- `/metrics` — Prometheus-text format when `prometheus_client` is installed, JSON
  otherwise: request count, average latency, class-prediction distribution.
  

- `/dashboard/metrics` — richer JSON purpose-built for the live dashboard UI: request
  count, error count/rate, average latency, uptime, class distribution, total bytes
  processed, payload throughput (KB/s), host CPU %, host memory %, and a rolling
  window of the last 50 requests (timestamp + latency + label) for the live charts.
- **Prometheus + Grafana (Kubernetes)**: `deployment/k8s/servicemonitor.yaml` provides a
  `ServiceMonitor` for Prometheus Operator and `PrometheusRule` with alerts (high error
  rate, high latency, service down). `deployment/k8s/grafana-dashboard.yaml` is a
  ConfigMap with a pre-built Grafana dashboard (auto-discovered by Grafana if labeled
  `grafana_dashboard=1`).
  
- **Prometheus + Grafana (local)**: `deployment/monitoring/docker-compose.yml` spins up
  Prometheus (port 9090) and Grafana (port 3000, admin/admin) with the same dashboard
  pre-provisioned.
- `scripts/simulate_traffic.py` fires a batch of requests with known labels against a
  running deployment and reports batch accuracy — the "post-deployment performance
  tracking" artifact:

```bash
python scripts/simulate_traffic.py --url http://localhost:8000 --data-dir data/processed/test --n 30
```

- **New (M5)**: `scripts/track_performance.py` — standalone performance tracking that
  collects predictions from the deployed service, simulates ground truth labels, and
  computes accuracy/precision/recall/F1/confusion matrix + latency percentiles:

```bash
# Local (port-forward)
python scripts/track_performance.py --url http://localhost:8091 --samples 50

# Via ngrok
python scripts/track_performance.py --url https://octane-hardcore-pursuable.ngrok-free.dev --samples 100
```

## 10. Demo recording checklist (<5 min)

1. Make a small code change (e.g. tweak a docstring or threshold).
2. `git push` → show GitHub Actions CI run (tests pass, image builds, pushes to ghcr.io).
3. Show CD run on merge to `main` (Compose or Kubernetes path — pulls/redeploys the
   new image, smoke test passes).
4. Open `/ui/test-console/`, drag in a photo, show the stamped prediction.
5. Open `/ui/dashboard/`, fire a few more predictions, watch the live latency line,
   request count, and class-distribution chart update.
6. Show MLflow UI with the logged run (params/metrics/confusion matrix).
7. Show `simulate_traffic.py` batch-accuracy result against the live deployment.

