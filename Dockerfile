FROM python:3.11-slim

WORKDIR /app

# System deps needed by Pillow/torch runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# TARGETARCH is set automatically by Buildx per-platform during a multi-arch
# build (amd64, arm64, etc.) - no need to pass it yourself.
#
# The download.pytorch.org/whl/cpu index only publishes x86_64 (amd64)
# wheels, which is why it's used here to force the small CPU-only build
# instead of the much larger default CUDA-bundled one. It has no arm64
# wheels at all, so using it unconditionally makes the arm64 build stage
# fail to resolve torch (or silently produce no image for that platform,
# depending on the Buildx/pip failure mode) - which is what caused
# "no match for platform in manifest: not found" when pulling on an arm64
# node (e.g. kind on Apple Silicon). On arm64, fall back to plain PyPI,
# which does publish manylinux_aarch64 CPU wheels for the pinned torch
# version in requirements.txt.
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        pip install --no-cache-dir -r requirements.txt \
            --extra-index-url https://download.pytorch.org/whl/cpu; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY src/ ./src/
COPY api/ ./api/
COPY ui/ ./ui/
COPY artifacts/ ./artifacts/

ENV MODEL_PATH=/app/artifacts/model.pt
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
