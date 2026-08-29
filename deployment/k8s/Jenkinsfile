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
//                        (see deployment/argocd/project.yaml)
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
        IMAGE_NAME       = 'OWNER/REPO/pet-classifier'   // <-- set to your actual image path
        NAMESPACE        = 'pet-adoption'
        ARGOCD_APP       = 'pet-classifier'
        ARGOCD_SERVER    = 'argocd.internal.example.com'  // <-- set to your ArgoCD server address
        GIT_REPO_URL     = 'git@github.com:OWNER/REPO.git' // <-- set to your actual repo (SSH form for push)
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
                        export GIT_SSH_COMMAND="ssh -i \$SSH_KEY -o StrictHostKeyChecking=no"
                        git config user.email "jenkins-ci@pet-adoption.local"
                        git config user.name "jenkins-ci"
                        git add deployment/k8s/kustomization.yaml
                        git commit -m "deploy: pet-classifier:${params.IMAGE_TAG} [jenkins-cd]" || echo "No changes to commit (tag already deployed)"
                        git push ${GIT_REPO_URL} HEAD:${GIT_BRANCH}
                    """
                }
            }
        }

        stage('ArgoCD login') {
            steps {
                withCredentials([string(credentialsId: 'argocd-auth-token', variable: 'ARGOCD_TOKEN')]) {
                    sh """
                        argocd login ${ARGOCD_SERVER} --auth-token \$ARGOCD_TOKEN --grpc-web
                    """
                }
            }
        }

        stage('Sync via ArgoCD') {
            steps {
                sh """
                    argocd app sync ${ARGOCD_APP} --prune --timeout 180
                    argocd app wait ${ARGOCD_APP} --health --timeout 180
                """
            }
        }

        stage('Smoke test') {
            steps {
                withCredentials([
                    file(credentialsId: 'kubeconfig-cd', variable: 'KUBECONFIG'),
                    string(credentialsId: 'pet-classifier-api-key', variable: 'API_KEY_FOR_SMOKE_TEST')
                ]) {
                    sh '''
                        set -e
                        kubectl port-forward -n "$NAMESPACE" svc/pet-classifier-svc 8080:80 &
                        PF_PID=$!
                        sleep 5
                        trap "kill $PF_PID" EXIT

                        echo "Health check:"
                        for i in $(seq 1 10); do
                          if curl -sf http://localhost:8080/health; then
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
                        response=$(curl -sf -H "X-API-Key: $API_KEY_FOR_SMOKE_TEST" -F "file=@sample_test.jpg" http://localhost:8080/predict)
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
                sh """
                    argocd login ${ARGOCD_SERVER} --auth-token \$ARGOCD_TOKEN --grpc-web || true
                    argocd app history ${ARGOCD_APP} || true
                    argocd app rollback ${ARGOCD_APP} || true
                """
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
