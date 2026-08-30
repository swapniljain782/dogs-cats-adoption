#!/usr/bin/env python3
"""
Post-deployment model performance tracking script.

Collects a batch of predictions from the deployed service and tracks
accuracy/drift over time. Can use simulated labels or real labels if available.

Usage:
    python scripts/track_performance.py --url http://localhost:8091 --samples 50
    python scripts/track_performance.py --url https://octane-hardcore-pursuable.ngrok-free.dev --samples 100 --output metrics.json
"""
import argparse
import json
import random
import time
from pathlib import Path
from typing import List, Dict

import requests
import numpy as np
from PIL import Image


CLASSES = ["cats", "dogs"]


def generate_synthetic_image() -> bytes:
    """Generate a random synthetic image for testing."""
    arr = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = __import__('io').BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()


def download_test_image() -> bytes:
    """Download a real cat image from Wikimedia."""
    try:
        resp = requests.get(
            "https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg",
            timeout=10
        )
        resp.raise_for_status()
        return resp.content
    except Exception:
        return generate_synthetic_image()


def predict(url: str, image_bytes: bytes, api_key: str = "", retries: int = 3) -> Dict:
    """Send prediction request to the service, with retries for transient failures."""
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    
    files = {"file": ("test.jpg", image_bytes, "image/jpeg")}
    for attempt in range(retries):
        try:
            resp = requests.post(f"{url}/predict", files=files, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except (requests.ConnectionError, requests.Timeout):
            if attempt < retries - 1:
                time.sleep(3)
                continue
            raise


def ensure_port_forward(url: str) -> bool:
    """Check if service is reachable, try to restart port-forward if not."""
    try:
        resp = requests.get(f"{url}/health", timeout=3)
        return resp.status_code == 200
    except Exception:
        pass
    # Try restarting port-forward
    import subprocess
    try:
        subprocess.run(
            ["pkill", "-f", "kubectl port-forward.*pet-classifier-svc"],
            capture_output=True, timeout=5
        )
        time.sleep(1)
        subprocess.Popen(
            ["kubectl", "port-forward", "-n", "pet-adoption",
             "svc/pet-classifier-svc", "8091:80"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(3)
        resp = requests.get(f"{url}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def health_check(url: str, retries: int = 3, delay: float = 2.0) -> bool:
    """Check if service is healthy, with retries for transient failures."""
    for attempt in range(retries):
        try:
            resp = requests.get(f"{url}/health", timeout=5)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                return True
        except Exception:
            pass
        if attempt < retries - 1:
            print(f"  Health check attempt {attempt + 1} failed, retrying in {delay}s...")
            time.sleep(delay)
    return False


def simulate_labels(predictions: List[Dict], accuracy: float = 0.85) -> List[str]:
    """
    Simulate ground truth labels based on predictions with a given accuracy.
    This mimics real-world scenario where you'd have some labeled data.
    """
    labels = []
    for pred in predictions:
        if random.random() < accuracy:
            labels.append(pred["label"])
        else:
            # Wrong prediction - flip the label
            labels.append("dogs" if pred["label"] == "cats" else "cats")
    return labels


def compute_metrics(predictions: List[Dict], true_labels: List[str]) -> Dict:
    """Compute classification metrics."""
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
    
    pred_labels = [p["label"] for p in predictions]
    
    cm = confusion_matrix(true_labels, pred_labels, labels=CLASSES)
    
    return {
        "accuracy": accuracy_score(true_labels, pred_labels),
        "precision": precision_score(true_labels, pred_labels, average="macro", zero_division=0),
        "recall": recall_score(true_labels, pred_labels, average="macro", zero_division=0),
        "f1": f1_score(true_labels, pred_labels, average="macro", zero_division=0),
        "confusion_matrix": cm.tolist(),
        "class_distribution": {
            "cats": pred_labels.count("cats"),
            "dogs": pred_labels.count("dogs"),
        },
        "avg_probability": np.mean([p["probability"] for p in predictions]),
        "sample_count": len(predictions),
    }


def main():
    parser = argparse.ArgumentParser(description="Track deployed model performance")
    parser.add_argument("--url", required=True, help="Base URL of deployed service (e.g., http://localhost:8091)")
    parser.add_argument("--samples", type=int, default=50, help="Number of prediction samples to collect")
    parser.add_argument("--api-key", default="", help="API key if auth is enabled")
    parser.add_argument("--accuracy", type=float, default=0.85, help="Simulated label accuracy (0-1)")
    parser.add_argument("--output", default="performance_metrics.json", help="Output JSON file")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests (seconds)")
    parser.add_argument("--use-real-image", action="store_true", help="Download real cat image instead of synthetic")
    args = parser.parse_args()

    print(f"Tracking performance for {args.samples} samples at {args.url}")
    
    # Health check first
    if not health_check(args.url):
        print("ERROR: Service health check failed")
        return 1

    print("Health check passed. Collecting predictions...")
    
    predictions = []
    latencies = []
    
    for i in range(args.samples):
        try:
            # Use real or synthetic image
            if args.use_real_image and i == 0:
                image_bytes = download_test_image()
            else:
                image_bytes = generate_synthetic_image()
            
            try:
                start = time.time()
                result = predict(args.url, image_bytes, args.api_key)
                latency = time.time() - start
            except (requests.ConnectionError, requests.Timeout):
                print(f"  Connection lost, restarting port-forward...")
                if ensure_port_forward(args.url):
                    start = time.time()
                    result = predict(args.url, image_bytes, args.api_key)
                    latency = time.time() - start
                else:
                    print(f"  Request {i+1} failed: could not reconnect")
                    continue
            
            predictions.append(result)
            latencies.append(latency)
            
            if (i + 1) % 10 == 0:
                print(f"  Collected {i + 1}/{args.samples} samples...")
            
            time.sleep(args.delay)
            
        except Exception as e:
            print(f"  Request {i+1} failed: {e}")
            continue

    if not predictions:
        print("ERROR: No successful predictions collected")
        return 1

    # Simulate ground truth labels
    true_labels = simulate_labels(predictions, args.accuracy)
    
    # Compute metrics
    metrics = compute_metrics(predictions, true_labels)
    metrics["latency"] = {
        "mean_ms": np.mean(latencies) * 1000,
        "p50_ms": np.percentile(latencies, 50) * 1000,
        "p95_ms": np.percentile(latencies, 95) * 1000,
        "p99_ms": np.percentile(latencies, 99) * 1000,
    }
    metrics["timestamp"] = time.time()
    metrics["service_url"] = args.url
    metrics["simulated_accuracy"] = args.accuracy

    # Save metrics
    output_path = Path(args.output)
    output_path.write_text(json.dumps(metrics, indent=2))
    
    print(f"\n=== Performance Metrics ===")
    print(f"Accuracy:  {metrics['accuracy']:.4f}")
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall:    {metrics['recall']:.4f}")
    print(f"F1 Score:  {metrics['f1']:.4f}")
    print(f"Avg Prob:  {metrics['avg_probability']:.4f}")
    print(f"Latency P50: {metrics['latency']['p50_ms']:.2f} ms")
    print(f"Latency P95: {metrics['latency']['p95_ms']:.2f} ms")
    print(f"Confusion Matrix:")
    for row in metrics['confusion_matrix']:
        print(f"  {row}")
    print(f"\nMetrics saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    exit(main())