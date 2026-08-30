FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    mlflow==2.14.1 \
    psycopg2-binary==2.9.9 \
    boto3==1.34.0 \
    scikit-learn==1.5.0 \
    torch==2.3.1 \
    torchvision==0.18.1 \
    --extra-index-url https://download.pytorch.org/whl/cpu

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

CMD ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000"]
