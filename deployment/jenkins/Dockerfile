# Jenkins CONTROLLER image (serves the web UI, runs pipelines) with
# kubectl/kustomize/argocd CLI + python3 baked in. Built from
# jenkins/jenkins:lts - NOT jenkins/inbound-agent, which is a build-AGENT
# image that connects outward to a separate controller via JNLP and does not
# serve a web UI at all. Deploying an inbound-agent image as if it were the
# controller crashes immediately (it starts, looks for a controller to
# connect to, finds none, exits) - that's the "Back-off restarting" loop
# this file fixes.
#
#   docker build -t jenkins-agent:latest -f deployment/jenkins/Dockerfile .
#   docker tag jenkins-agent:latest ghcr.io/swapniljain782/dogs-cats-adoption/jenkins-agent:latest
#   docker push ghcr.io/swapniljain782/dogs-cats-adoption/jenkins-agent:latest

FROM jenkins/jenkins:lts

USER root

ARG KUBECTL_VERSION=v1.30.0
ARG KUSTOMIZE_VERSION=v5.4.3
ARG ARGOCD_VERSION=v2.11.0

# git already ships in jenkins/jenkins:lts - python3 does not, and the
# Jenkinsfile's smoke test needs it (fallback test-image generation via
# numpy/Pillow, plus parsing the /predict JSON response).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        python3 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages numpy Pillow

RUN curl -fsSL -o /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    && chmod +x /usr/local/bin/kubectl

RUN curl -fsSL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2F${KUSTOMIZE_VERSION}/kustomize_${KUSTOMIZE_VERSION}_linux_amd64.tar.gz" \
        | tar -xz -C /usr/local/bin/

RUN curl -fsSL -o /usr/local/bin/argocd \
        "https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-amd64" \
    && chmod +x /usr/local/bin/argocd

USER jenkins
