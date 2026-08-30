#!/usr/bin/env bash
# port-forward.sh — Start/stop all service port-forwards for the pet-adoption platform.
#
# Usage:
#   ./port-forward.sh          # start all port-forwards
#   ./port-forward.sh start    # start all port-forwards
#   ./port-forward.sh stop     # kill all port-forwards
#   ./port-forward.sh status   # show running port-forwards
set -euo pipefail

# ── Local ports (change here if you have conflicts) ──────────────────────────
PET_CLASSIFIER_PORT=8091
MLFLOW_UI_PORT=5000
MINIO_CONSOLE_PORT=9001
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
JENKINS_PORT=8080
ARGOCD_PORT=8443

# ── Service names ────────────────────────────────────────────────────────────
PET_SVC="svc/pet-classifier-svc"
MLFLOW_SVC="svc/mlflow-server"
MINIO_SVC="svc/mlflow-minio"
PROM_SVC="svc/prometheus-kube-prometheus-prometheus"
GRAFANA_SVC="svc/prometheus-grafana"
JENKINS_SVC="svc/jenkins"
ARGOCD_SVC="svc/argocd-server"

PIDFILE="/tmp/pet-adoption-portforward.pids"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

stop_all() {
    echo -e "${YELLOW}Stopping all port-forwards...${NC}"
    if [[ -f "$PIDFILE" ]]; then
        while IFS= read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null && echo -e "  ${RED}Killed PID $pid${NC}"
            fi
        done < "$PIDFILE"
        rm -f "$PIDFILE"
    fi
    # Fallback: kill anything matching our pattern
    pkill -f "kubectl port-forward -n (pet-adoption|monitoring|jenkins|argocd)" 2>/dev/null || true
    echo -e "${GREEN}All port-forwards stopped.${NC}"
}

show_status() {
    echo -e "${CYAN}Running port-forwards:${NC}"
    if [[ -f "$PIDFILE" ]]; then
        local count=0
        while IFS= read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                local cmd
                cmd=$(ps -p "$pid" -o command= 2>/dev/null | head -c 120)
                echo -e "  ${GREEN}PID $pid${NC}  $cmd"
                ((count++))
            fi
        done < "$PIDFILE"
        if [[ $count -eq 0 ]]; then
            echo -e "  ${YELLOW}No active port-forwards.${NC}"
        fi
    else
        echo -e "  ${YELLOW}No port-forwards have been started from this script.${NC}"
    fi
}

start_all() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║       Pet Adoption Platform — Port-Forward All          ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Kill existing port-forwards first
    stop_all 2>/dev/null
    rm -f "$PIDFILE"
    touch "$PIDFILE"

    # ── 1. Pet Classifier API ───────────────────────────────────────────────
    kubectl port-forward -n pet-adoption "$PET_SVC" "${PET_CLASSIFIER_PORT}:80" &>/dev/null &
    echo $! >> "$PIDFILE"
    echo -e "  ${GREEN}✓${NC} Pet Classifier API          → http://localhost:${PET_CLASSIFIER_PORT}"
    echo -e "    ${YELLOW}├─${NC} /health"
    echo -e "    ${YELLOW}├─${NC} /predict"
    echo -e "    ${YELLOW}├─${NC} /ui/test-console/"
    echo -e "    ${YELLOW}└─${NC} /ui/dashboard/"

    # ── 2. MLflow Tracking Server ───────────────────────────────────────────
    kubectl port-forward -n pet-adoption "$MLFLOW_SVC" "${MLFLOW_UI_PORT}:5000" &>/dev/null &
    echo $! >> "$PIDFILE"
    echo -e "  ${GREEN}✓${NC} MLflow Tracking Server       → http://localhost:${MLFLOW_UI_PORT}"

    # ── 3. MinIO Console ───────────────────────────────────────────────────
    kubectl port-forward -n pet-adoption "$MINIO_SVC" "${MINIO_CONSOLE_PORT}:9001" &>/dev/null &
    echo $! >> "$PIDFILE"
    echo -e "  ${GREEN}✓${NC} MinIO Console                → http://localhost:${MINIO_CONSOLE_PORT}"
    echo -e "    ${YELLOW}└─${NC} Login: mlflow / mlflow123"

    # ── 4. Prometheus ──────────────────────────────────────────────────────
    kubectl port-forward -n monitoring "$PROM_SVC" "${PROMETHEUS_PORT}:9090" &>/dev/null &
    echo $! >> "$PIDFILE"
    echo -e "  ${GREEN}✓${NC} Prometheus                   → http://localhost:${PROMETHEUS_PORT}"

    # ── 5. Grafana ─────────────────────────────────────────────────────────
    kubectl port-forward -n monitoring "$GRAFANA_SVC" "${GRAFANA_PORT}:80" &>/dev/null &
    echo $! >> "$PIDFILE"
    echo -e "  ${GREEN}✓${NC} Grafana                      → http://localhost:${GRAFANA_PORT}"
    echo -e "    ${YELLOW}└─${NC} Login: admin / admin"

    # ── 6. Jenkins ─────────────────────────────────────────────────────────
    kubectl port-forward -n jenkins "$JENKINS_SVC" "${JENKINS_PORT}:8080" &>/dev/null &
    echo $! >> "$PIDFILE"
    echo -e "  ${GREEN}✓${NC} Jenkins                      → http://localhost:${JENKINS_PORT}"

    # ── 7. ArgoCD ──────────────────────────────────────────────────────────
    kubectl port-forward -n argocd "$ARGOCD_SVC" "${ARGOCD_PORT}:443" &>/dev/null &
    echo $! >> "$PIDFILE"
    echo -e "  ${GREEN}✓${NC} ArgoCD                       → https://localhost:${ARGOCD_PORT}"

    echo ""
    echo -e "${CYAN}──────────────────────────────────────────────────────────${NC}"
    echo -e "  Run ${YELLOW}./port-forward.sh stop${NC} to kill all port-forwards"
    echo -e "  Run ${YELLOW}./port-forward.sh status${NC} to see running PIDs"
    echo -e "${CYAN}──────────────────────────────────────────────────────────${NC}"
}

# ── Main ─────────────────────────────────────────────────────────────────────
case "${1:-start}" in
    start)  start_all ;;
    stop)   stop_all ;;
    status) show_status ;;
    restart)
        stop_all 2>/dev/null
        sleep 1
        start_all
        ;;
    jenkins-on)
        echo -e "${GREEN}Scaling Jenkins to 1 replica...${NC}"
        kubectl scale deployment jenkins -n jenkins --replicas=1
        kubectl rollout status deployment/jenkins -n jenkins --timeout=120s
        # Also start Jenkins port-forward
        pkill -f "kubectl port-forward -n jenkins" 2>/dev/null || true
        nohup kubectl port-forward -n jenkins "$JENKINS_SVC" "${JENKINS_PORT}:8080" &>/dev/null &
        echo -e "${GREEN}✓${NC} Jenkins is running → http://localhost:${JENKINS_PORT}"
        ;;
    jenkins-off)
        echo -e "${YELLOW}Scaling Jenkins to 0 replicas (frees ~1GB)...${NC}"
        pkill -f "kubectl port-forward -n jenkins" 2>/dev/null || true
        kubectl scale deployment jenkins -n jenkins --replicas=0
        echo -e "${GREEN}Jenkins scaled down.${NC}"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|jenkins-on|jenkins-off}"
        exit 1
        ;;
esac
