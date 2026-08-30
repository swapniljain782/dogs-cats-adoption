// Jenkinsfile — CD pipeline for the Pet Adoption Cats-vs-Dogs classifier.
//
// Responsibility split:
//   GitHub Actions (ci.yml)  -> test, build image, push to ghcr.io           [CI]
//   Jenkins (this file)      -> bump the GitOps manifest, verify ArgoCD     [CD]
//                                sync'd it, smoke test, roll back on failure
//   ArgoCD                   -> owns the actual `kubectl apply` - it watches
//                                the git repo and reconciles the cluster to
//                                match deployment/k8s (config management)
//
// Trigger: called by ci.yml via a parameterized remote build trigger once a
// new image has been pushed to main, e.g.:
//   curl -u "$JENKINS_USER:$JENKINS_TOKEN" \
//     "$JENKINS_URL/job/pet-classifier-cd/buildWithParameters?IMAGE_TAG=<git-sha>"
//
// Required Jenkins credentials (Manage Jenkins > Credentials):
//   git-push-creds   - SSH key or PAT with push access to this repo (for the
//                       manifest-bump commit)
//   argocd-auth-token - ArgoCD auth token for the "ci-deployer" project role
//                        (see deployment/argocd/project.yaml). Passed as a
//                        --auth-token flag directly on every argocd command -
//                        NOT via `argocd login`, which is built around
//                        interactive/SSO sessions and doesn't handle
//                        non-interactive token auth cleanly in this setup.
//   kubeconfig-cd     - kubeconfig for the target cluster (smoke test only)
//   pet-classifier-api-key - (Secret text) the same value stored in the
//                        cluster's `pet-classifier-secrets` Secret, so the
//                        smoke test can authenticate if API-key auth is
//                        enabled. Leave empty (empty Secret text credential)
//                        if the deployment doesn't require a key.
//
// Required tools on the Jenkins agent (or use jenkins/Dockerfile.agent):
//   git, kustomize, argocd CLI, kubectl, python3

pipeline {
    agent any

    parameters {
        string(name: 'IMAGE_TAG', defaultValue: 'latest', description: 'Image tag pushed by CI (git SHA recommended over "latest")')
    }

    environment {
        REGISTRY        = 'ghcr.io'
        IMAGE_NAME       = 'swapniljain782/dogs-cats-adoption/pet-classifier'
        NAMESPACE        = 'pet-adoption'
        ARGOCD_APP       = 'pet-classifier'
        // Jenkins runs *inside* the cluster (see deployment/k8s/jenkins.yaml),
        // so it reaches ArgoCD via the in-cluster Service DNS name - not
        // localhost/port-forward, which only means something from your own
        // machine. Default namespace/service name from install-argocd.sh.
        ARGOCD_SERVER    = 'argocd-server.argocd.svc.cluster.local:443'
        // Every argocd CLI call below passes --server/--auth-token/--insecure
        // directly rather than using `argocd login` first - the stateful
        // login flow is built around interactive/SSO sessions, and kept
        // falling back to an interactive username prompt (which hangs
        // forever in a non-interactive CI shell) even with --auth-token set.
        // Passing the token as a flag on every command is the documented
        // pattern for non-interactive API-token auth and skips that flow
        // entirely: https://www.arthurkoziel.com/creating-argo-cd-service-account/
        ARGOCD_FLAGS     = '--grpc-web --insecure'
        GIT_REPO_URL     = 'git@github.com:swapniljain782/dogs-cats-adoption.git'
        GIT_BRANCH       = 'main'
        // kubectl/kustomize/argocd live here (see deployment/k8s/jenkins.yaml's
        // initContainer) since the Jenkins controller pod doesn't run these
        // pipeline steps on a separate agent - it's all-in-one for this setup.
        // ${env.PATH} reads the container's actual runtime PATH, so this only
        // prepends - it doesn't clobber whatever the base image already set.
        PATH = "/opt/devtools:${env.PATH}"
    }

    options {
        timestamps()
        timeout(time: 20, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Bump image tag (GitOps manifest update)') {
            steps {
                dir('deployment/k8s') {
                    sh """
                        kustomize edit set image ${REGISTRY}/${IMAGE_NAME}=${REGISTRY}/${IMAGE_NAME}:${params.IMAGE_TAG}
                    """
                }
                withCredentials([sshUserPrivateKey(credentialsId: 'git-push-creds', keyFileVariable: 'SSH_KEY')]) {
                    sh """
                        # BatchMode=yes disables any interactive auth fallback (password/
                        # keyboard-interactive prompts) - without it, a failed key auth
                        # silently hangs waiting for input from a closed stdin until
                        # GitHub's idle timeout kicks in (~10 min), instead of failing
                        # immediately with a clear "Permission denied (publickey)".
                        # ConnectTimeout bounds the initial TCP/handshake phase too.
                        export GIT_SSH_COMMAND="ssh -i \$SSH_KEY -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=15"
                        git config user.email "jenkins-ci@pet-adoption.local"
                        git config user.name "jenkins-ci"
                        git add deployment/k8s/kustomization.yaml
                        git commit -m "deploy: pet-classifier:${params.IMAGE_TAG} [jenkins-cd]" || echo "No changes to commit (tag already deployed)"
                        git push ${GIT_REPO_URL} HEAD:${GIT_BRANCH}
                    """
                }
            }
        }

        stage('Sync via ArgoCD') {
            steps {
                withCredentials([string(credentialsId: 'argocd-auth-token', variable: 'ARGOCD_TOKEN')]) {
                    sh '''
                        echo "ARGOCD_TOKEN length: ${#ARGOCD_TOKEN}"
                        if [ -z "$ARGOCD_TOKEN" ]; then
                            echo "ERROR: argocd-auth-token credential is empty - check its value in Jenkins credentials."
                            exit 1
                        fi
                        argocd app sync "$ARGOCD_APP" --server "$ARGOCD_SERVER" --auth-token "$ARGOCD_TOKEN" $ARGOCD_FLAGS --prune --timeout 180
                        argocd app wait "$ARGOCD_APP" --server "$ARGOCD_SERVER" --auth-token "$ARGOCD_TOKEN" $ARGOCD_FLAGS --health --timeout 180
                    '''
                }
            }
        }

        stage('Smoke test') {
            steps {
                // No kubeconfig-cd credential here: this runs in-cluster
                // under the jenkins-deployer ServiceAccount attached to the
                // Jenkins pod (see deployment/k8s/jenkins.yaml's
                // serviceAccountName + deployment/k8s/jenkins-rbac.yaml),
                // so kubectl auto-detects in-cluster auth from the mounted
                // SA token. A stale/previously-generated kubeconfig file
                // credential can carry an OLD ServiceAccount's token (e.g.
                // from before jenkins-deployer was moved into the jenkins
                // namespace) that no longer has RBAC granted to it -
                // exactly the "Forbidden ... jenkins-deployer" error this
                // caused. Do not reintroduce a kubeconfig-cd credential here.
                withCredentials([
                    string(credentialsId: 'pet-classifier-api-key', variable: 'API_KEY_FOR_SMOKE_TEST')
                ]) {
                    sh '''
                        set -e
                        # Kill any leftover port-forward from a previous failed/aborted
                        # build that didn't get cleaned up (this build's own port-forward
                        # otherwise fails to bind if one's still running).
                        pkill -f "kubectl port-forward.*pet-classifier-svc" || true
                        sleep 1

                        # Port 8090, not 8080: this pipeline runs with `agent any`, so
                        # these steps execute directly inside the Jenkins controller
                        # container itself - which already has its OWN web UI bound to
                        # 8080. Forwarding to 8080 here collides with Jenkins itself, not
                        # anything on your host machine.
                        kubectl port-forward -n "$NAMESPACE" svc/pet-classifier-svc 8090:80 &
                        PF_PID=$!
                        sleep 5
                        trap "kill $PF_PID" EXIT

                        echo "Health check:"
                        for i in $(seq 1 10); do
                          if curl -sf http://localhost:8090/health; then
                            echo "Health check passed"
                            break
                          fi
                          [ "$i" -eq 10 ] && { echo "Health check failed"; exit 1; }
                          sleep 3
                        done

                        echo "Prediction check:"
                        curl -sf -o sample_test.jpg https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg || \
                          python3 -c "
import numpy as np
from PIL import Image
Image.fromarray(np.random.randint(0,255,(224,224,3),dtype='uint8')).save('sample_test.jpg')
"
                        # -H is a no-op if API auth is disabled on this deployment;
                        # required if the Secret in secret.yaml is populated.
                        response=$(curl -sf -H "X-API-Key: $API_KEY_FOR_SMOKE_TEST" -F "file=@sample_test.jpg" http://localhost:8090/predict)
                        echo "Prediction response: $response"
                        echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'label' in d and 'probability' in d"
                    '''
                }
            }
        }
    }

    post {
        failure {
            echo "Smoke test or sync failed - rolling back via ArgoCD."
            withCredentials([string(credentialsId: 'argocd-auth-token', variable: 'ARGOCD_TOKEN')]) {
                sh '''
                    argocd app history "$ARGOCD_APP" --server "$ARGOCD_SERVER" --auth-token "$ARGOCD_TOKEN" $ARGOCD_FLAGS || true
                    argocd app rollback "$ARGOCD_APP" --server "$ARGOCD_SERVER" --auth-token "$ARGOCD_TOKEN" $ARGOCD_FLAGS || true
                '''
            }
        }
        always {
            sh 'pkill -f "kubectl port-forward" || true'
        }
        success {
            echo "Deployed pet-classifier:${params.IMAGE_TAG} to ${NAMESPACE} - ArgoCD in sync, smoke test passed."
        }
    }
}
