"""
FastAPI inference service for the Cats vs Dogs classifier.

Endpoints:
    GET  /health            - liveness/readiness check
    POST /predict           - accepts an image file, returns predicted label + probabilities
    GET  /metrics           - Prometheus text metrics (falls back to JSON if prometheus_client absent)
    GET  /dashboard/metrics - JSON metrics + recent-request history, for the live dashboard UI
    GET  /ui/test-console   - model testing UI (upload an image, see the prediction)
    GET  /ui/dashboard      - live monitoring UI (usage, latency, utilization)
"""
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.utils.inference import load_model, predict_image_bytes
from api.schemas import HealthResponse, PredictResponse, MetricsResponse

try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("pet-classifier")

MODEL_PATH = os.environ.get("MODEL_PATH", "artifacts/model.pt")
UI_DIR = Path(__file__).resolve().parent.parent / "ui"
HISTORY_MAXLEN = 200  # how many recent requests to keep for the dashboard's live charts

app = FastAPI(title="Pet Adoption - Cats vs Dogs Classifier", version="1.0.0")

# --- in-memory metrics (simple counters; excludes any request payload/PII) ---
_start_time = time.time()
_metrics_state = {
    "request_count": 0,
    "error_count": 0,
    "total_latency_ms": 0.0,
    "total_bytes_processed": 0,
    "predictions": {"cats": 0, "dogs": 0},
}
# Rolling window of recent requests, used purely for the live dashboard's charts.
# Each entry: {ts, latency_ms, label, bytes, status}
_request_history: Deque[dict] = deque(maxlen=HISTORY_MAXLEN)

if _PROMETHEUS_AVAILABLE:
    PROM_REQUEST_COUNT = Counter("predict_requests_total", "Total prediction requests")
    PROM_LATENCY = Histogram("predict_latency_seconds", "Prediction latency in seconds")
    PROM_PREDICTIONS = Counter("predictions_by_class_total", "Predictions by class", ["label"])

_model = None


@app.on_event("startup")
def _startup():
    global _model
    try:
        _model = load_model(MODEL_PATH)
        logger.info("Model loaded from %s", MODEL_PATH)
    except FileNotFoundError as e:
        _model = None
        logger.warning("Model not loaded at startup: %s", e)


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    # Log method/path/status/latency only - never log request bodies (may contain images).
    logger.info(
        "%s %s -> %s (%.2f ms)",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", model_loaded=_model is not None)


@app.post("/predict", response_model=PredictResponse)
async def predict(file: UploadFile = File(...)):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded on this instance")

    if file.content_type not in ("image/jpeg", "image/png", "image/jpg"):
        raise HTTPException(status_code=400, detail="Only JPEG/PNG images are supported")

    start = time.time()
    image_bytes = await file.read()

    try:
        result = predict_image_bytes(_model, image_bytes)
    except Exception as e:
        logger.exception("Prediction failed")
        _metrics_state["error_count"] += 1
        _request_history.append({
            "ts": time.time(), "latency_ms": (time.time() - start) * 1000,
            "label": None, "bytes": len(image_bytes), "status": "error",
        })
        raise HTTPException(status_code=422, detail=f"Could not process image: {e}")

    latency_ms = (time.time() - start) * 1000

    _metrics_state["request_count"] += 1
    _metrics_state["total_latency_ms"] += latency_ms
    _metrics_state["total_bytes_processed"] += len(image_bytes)
    _metrics_state["predictions"][result["label"]] += 1
    _request_history.append({
        "ts": time.time(), "latency_ms": latency_ms,
        "label": result["label"], "bytes": len(image_bytes), "status": "ok",
    })

    if _PROMETHEUS_AVAILABLE:
        PROM_REQUEST_COUNT.inc()
        PROM_LATENCY.observe(latency_ms / 1000.0)
        PROM_PREDICTIONS.labels(label=result["label"]).inc()

    return PredictResponse(**result)


@app.get("/metrics")
def metrics():
    """Prometheus-scrapeable text metrics (falls back to a simple JSON summary)."""
    if _PROMETHEUS_AVAILABLE:
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    count = _metrics_state["request_count"]
    avg_latency = _metrics_state["total_latency_ms"] / count if count else 0.0
    return MetricsResponse(
        request_count=count,
        average_latency_ms=avg_latency,
        predictions=_metrics_state["predictions"],
    )


@app.get("/dashboard/metrics")
def dashboard_metrics():
    """
    Rich JSON metrics for the live monitoring dashboard UI.

    Note on "utilization": this is an image classifier, not an LLM, so there is
    no token count. The dashboard tracks the closest real equivalents instead:
    request throughput (images/sec), payload throughput (KB/s of image bytes
    processed - the image-model analog of token throughput), and host compute
    utilization (CPU/RAM), alongside the usual request count/latency/error rate.
    """
    count = _metrics_state["request_count"]
    uptime_s = time.time() - _start_time
    avg_latency = _metrics_state["total_latency_ms"] / count if count else 0.0

    # Compute utilization - host CPU/RAM the service is consuming right now.
    if _PSUTIL_AVAILABLE:
        cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        mem_percent = mem.percent
    else:
        cpu_percent = None
        mem_percent = None

    # Payload throughput over the visible history window (KB/s), the image-model
    # stand-in for "token utilization" on an LLM dashboard.
    recent = list(_request_history)
    if len(recent) >= 2:
        window_s = max(recent[-1]["ts"] - recent[0]["ts"], 1e-6)
        window_bytes = sum(r["bytes"] for r in recent)
        throughput_kb_s = (window_bytes / 1024.0) / window_s
    else:
        throughput_kb_s = 0.0

    return {
        "request_count": count,
        "error_count": _metrics_state["error_count"],
        "average_latency_ms": round(avg_latency, 2),
        "uptime_seconds": round(uptime_s, 1),
        "predictions": _metrics_state["predictions"],
        "total_bytes_processed": _metrics_state["total_bytes_processed"],
        "throughput_kb_per_sec": round(throughput_kb_s, 2),
        "cpu_percent": cpu_percent,
        "memory_percent": mem_percent,
        "model_loaded": _model is not None,
        "recent_requests": [
            {
                "ts": r["ts"],
                "latency_ms": round(r["latency_ms"], 2),
                "label": r["label"],
                "bytes": r["bytes"],
                "status": r["status"],
            }
            for r in recent[-50:]  # last 50 points is plenty for a live chart
        ],
    }


# --- Static UI mounts ---------------------------------------------------
# /ui/test-console -> model testing console (upload an image, see the prediction)
# /ui/dashboard     -> live monitoring dashboard (usage, latency, utilization)
if UI_DIR.exists():
    app.mount("/ui/test-console", StaticFiles(directory=str(UI_DIR / "test-console"), html=True), name="test-console")
    app.mount("/ui/dashboard", StaticFiles(directory=str(UI_DIR / "dashboard"), html=True), name="dashboard")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/test-console/")
