"""
Post-deploy smoke test: checks /health and fires one /predict call.
Exits non-zero on failure so it can gate a CI/CD job.

Usage:
    python scripts/smoke_test.py --host localhost --port 8000
"""
import argparse
import io
import sys

import numpy as np
import requests
from PIL import Image


def make_dummy_image_bytes() -> bytes:
    arr = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG")
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--retries", type=int, default=10)
    parser.add_argument("--delay", type=float, default=3.0)
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    print(f"Checking {base_url}/health ...")
    healthy = False
    for attempt in range(1, args.retries + 1):
        try:
            resp = requests.get(f"{base_url}/health", timeout=5)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                healthy = True
                break
        except requests.RequestException:
            pass
        print(f"  retry {attempt}/{args.retries}...")
        import time
        time.sleep(args.delay)

    if not healthy:
        print("FAIL: health check did not pass")
        sys.exit(1)
    print("OK: health check passed")

    print(f"Checking {base_url}/predict ...")
    image_bytes = make_dummy_image_bytes()
    resp = requests.post(
        f"{base_url}/predict",
        files={"file": ("smoke_test.jpg", image_bytes, "image/jpeg")},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"FAIL: /predict returned {resp.status_code}: {resp.text}")
        sys.exit(1)

    data = resp.json()
    if "label" not in data or "probability" not in data:
        print(f"FAIL: unexpected /predict response shape: {data}")
        sys.exit(1)

    print(f"OK: /predict responded with label={data['label']} probability={data['probability']:.3f}")
    print("\nSmoke test passed.")


if __name__ == "__main__":
    main()
