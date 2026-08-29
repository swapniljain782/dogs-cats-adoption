"""
Simulate a small batch of production traffic against the deployed inference
service and report accuracy against known labels (post-deployment performance
tracking, M5).

Usage:
    python scripts/simulate_traffic.py --url http://localhost:8000 --data-dir data/processed/test --n 30
"""
import argparse
import random
import time
from pathlib import Path

import requests


def collect_samples(data_dir: Path, n: int, seed: int = 0):
    samples = []
    for cls in ("cats", "dogs"):
        class_dir = data_dir / cls
        if not class_dir.exists():
            continue
        for p in class_dir.iterdir():
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                samples.append((p, cls))
    random.Random(seed).shuffle(samples)
    return samples[:n]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", type=str, default="http://localhost:8000")
    parser.add_argument("--data-dir", type=str, default="data/processed/test")
    parser.add_argument("--n", type=int, default=30)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    samples = collect_samples(data_dir, args.n)

    if not samples:
        print(f"No labeled test images found under {data_dir}. "
              "Run preprocessing first, or point --data-dir at a labeled folder.")
        return

    correct, total, latencies = 0, 0, []

    for path, true_label in samples:
        with open(path, "rb") as f:
            start = time.time()
            resp = requests.post(
                f"{args.url}/predict",
                files={"file": (path.name, f, "image/jpeg")},
                timeout=10,
            )
            latencies.append(time.time() - start)

        if resp.status_code != 200:
            print(f"  [WARN] {path.name}: request failed ({resp.status_code})")
            continue

        pred_label = resp.json()["label"]
        total += 1
        if pred_label == true_label:
            correct += 1
        else:
            print(f"  [MISS] {path.name}: true={true_label} pred={pred_label}")

    acc = correct / total if total else 0.0
    avg_latency_ms = (sum(latencies) / len(latencies)) * 1000 if latencies else 0.0

    print("\n--- Simulated traffic report ---")
    print(f"Requests sent   : {total}")
    print(f"Accuracy        : {acc:.2%}")
    print(f"Avg latency     : {avg_latency_ms:.1f} ms")

    metrics_resp = requests.get(f"{args.url}/metrics", timeout=5)
    print(f"\nService /metrics snapshot:\n{metrics_resp.text}")


if __name__ == "__main__":
    main()
