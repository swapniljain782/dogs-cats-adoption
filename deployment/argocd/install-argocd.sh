#!/usr/bin/env bash
# Installs ArgoCD into a cluster (e.g. the local `kind` cluster from
# deployment/k8s/local-kind-deploy.sh) and registers the AppProject +
# Application so it starts watching this repo's deployment/k8s manifests.
#
# Usage:
#   ./deployment/argocd/install-argocd.sh
#
# Prereqs: kubectl pointed at your target cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Creating argocd namespace"
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -

echo "==> Installing ArgoCD core manifests"
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

echo "==> Waiting for argocd-server to be ready"
kubectl -n argocd rollout status deployment/argocd-server --timeout=300s

echo "==> Registering AppProject and Application"
# NOTE: edit application.yaml/project.yaml first to point sourceRepos/repoURL
# at your actual git remote (they default to a placeholder OWNER/REPO URL).
kubectl apply -f "${SCRIPT_DIR}/project.yaml"
kubectl apply -f "${SCRIPT_DIR}/application.yaml"

echo ""
echo "==> Initial admin password:"
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d
echo ""
echo ""
echo "Next steps:"
echo "  kubectl -n argocd port-forward svc/argocd-server 8080:443"
echo "  open https://localhost:8080  (user: admin, password printed above)"
echo ""
echo "Generate a CI role token for Jenkins with:"
echo "  argocd proj role create-token pet-adoption ci-deployer"
