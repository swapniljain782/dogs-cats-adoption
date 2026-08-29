#!/usr/bin/env bash
# Spin up a local kind cluster, load the locally built image, and deploy the
# service via kustomize - useful for demoing the k8s path without a registry.
#
# Usage:
#   ./deployment/k8s/local-kind-deploy.sh
#
# Prereqs: kind, kubectl, kustomize, docker all installed and on PATH.
set -euo pipefail

CLUSTER_NAME="pet-adoption"
IMAGE_TAG="pet-classifier:local"

echo "==> Building image locally"
docker build -t "${IMAGE_TAG}" .

echo "==> Creating kind cluster (if not already present)"
if ! kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  kind create cluster --name "${CLUSTER_NAME}" --config deployment/k8s/kind-config.yaml
else
  echo "    Cluster '${CLUSTER_NAME}' already exists, reusing it."
fi

echo "==> Loading image into kind"
kind load docker-image "${IMAGE_TAG}" --name "${CLUSTER_NAME}"

echo "==> Setting image reference via kustomize"
pushd deployment/k8s > /dev/null
kustomize edit set image ghcr.io/OWNER/REPO/pet-classifier="${IMAGE_TAG}"

echo "==> Applying manifests"
kustomize build . | kubectl apply -f -

echo "==> Applying NodePort service for local access"
kubectl apply -f service-nodeport.yaml
popd > /dev/null

echo "==> Waiting for rollout"
kubectl rollout status deployment/pet-classifier -n pet-adoption --timeout=180s

echo ""
echo "Ready. Try:"
echo "  curl http://localhost:30080/health"
echo "  open http://localhost:30080/ui/test-console/"
echo "  open http://localhost:30080/ui/dashboard/"
