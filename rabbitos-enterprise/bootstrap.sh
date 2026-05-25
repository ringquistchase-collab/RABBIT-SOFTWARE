#!/usr/bin/env bash
# RabbitOS Enterprise — Bootstrap Script
# Usage: ./bootstrap.sh [dev|staging|prod]
set -euo pipefail

ENV=${1:-prod}
REGION=${AWS_REGION:-us-east-1}
CLUSTER=rabbitos-enterprise
NAMESPACE=rabbitos

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[bootstrap]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
die()  { echo -e "${RED}[error]${NC} $*"; exit 1; }

check_deps() {
    log "Checking dependencies..."
    for cmd in terraform helm kubectl aws docker jq; do
        command -v "$cmd" &>/dev/null || die "Missing: $cmd"
        log "  $cmd $(${cmd} version --short 2>/dev/null | head -1 || true)"
    done
}

init_terraform() {
    log "Initialising Terraform (env=$ENV region=$REGION)..."
    cd terraform/aws
    terraform init \
        -backend-config="bucket=rabbitos-tfstate-${AWS_ACCOUNT_ID}" \
        -backend-config="key=${ENV}/terraform.tfstate" \
        -backend-config="region=${REGION}" \
        -reconfigure
    terraform workspace select "$ENV" 2>/dev/null || terraform workspace new "$ENV"
    terraform plan -var="env=${ENV}" -var="region=${REGION}" -out=tfplan
    read -rp "Apply infrastructure? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] && terraform apply tfplan || warn "Skipped apply."
    cd ../..
}

configure_kubectl() {
    log "Configuring kubectl..."
    aws eks update-kubeconfig --name "${CLUSTER}-${ENV}" --region "$REGION"
    kubectl cluster-info
}

deploy_charts() {
    log "Deploying Helm charts..."
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    # Infrastructure charts
    helm repo add bitnami   https://charts.bitnami.com/bitnami
    helm repo add qdrant    https://qdrant.github.io/qdrant-helm
    helm repo add neo4j     https://helm.neo4j.com/neo4j
    helm repo add prometheus https://prometheus-community.github.io/helm-charts
    helm repo add grafana   https://grafana.github.io/helm-charts
    helm repo update

    helm upgrade --install kafka      helm/kafka      -n "$NAMESPACE" --wait --timeout 5m
    helm upgrade --install qdrant     helm/qdrant     -n "$NAMESPACE" --wait --timeout 5m
    helm upgrade --install neo4j      helm/neo4j      -n "$NAMESPACE" --wait --timeout 5m
    helm upgrade --install prometheus helm/prometheus  -n monitoring  --create-namespace --wait
    helm upgrade --install grafana    helm/grafana    -n monitoring  --wait

    # Application chart
    helm upgrade --install rabbitos helm/rabbitos \
        -n "$NAMESPACE" \
        -f "helm/rabbitos/values.yaml" \
        -f "helm/rabbitos/values-${ENV}.yaml" 2>/dev/null || \
    helm upgrade --install rabbitos helm/rabbitos \
        -n "$NAMESPACE" \
        -f "helm/rabbitos/values.yaml" \
        --set global.env="$ENV" \
        --wait --timeout 10m

    log "All charts deployed."
}

smoke_test() {
    log "Running smoke tests..."
    GW=$(kubectl get svc rabbitos-gateway -n "$NAMESPACE" \
         -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "localhost")
    curl -sf "http://${GW}/health" | jq . && log "Gateway OK" || warn "Gateway not yet ready"
}

main() {
    log "RabbitOS Enterprise Bootstrap — env=${ENV}"
    [[ -f .env ]] && { log "Loading .env"; set -a; source .env; set +a; }
    check_deps
    init_terraform
    configure_kubectl
    deploy_charts
    smoke_test
    log "Bootstrap complete. Cluster: ${CLUSTER}-${ENV}"
}

main "$@"
