REGION  ?= us-east-1
CLUSTER ?= rabbitos-enterprise
ENV     ?= prod
NS      ?= rabbitos
REGISTRY ?= $(AWS_ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com
TAG     ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo latest)

.PHONY: all deploy destroy dev test lint build push logs clean

all: build push deploy

## ── Infrastructure ────────────────────────────────────────────────────────────
deploy:
	./bootstrap.sh $(ENV)

destroy:
	cd terraform/aws && terraform destroy -var="env=$(ENV)" -var="region=$(REGION)" -auto-approve

plan:
	cd terraform/aws && terraform plan -var="env=$(ENV)" -var="region=$(REGION)"

## ── Docker ────────────────────────────────────────────────────────────────────
build:
	docker build -t rabbitos-gateway:$(TAG)      services/gateway/
	docker build -t rabbitos-orchestrator:$(TAG) services/ai-orchestrator/
	docker build -t rabbitos-worker:$(TAG)       services/ai-workers/

push:
	aws ecr get-login-password --region $(REGION) | \
	  docker login --username AWS --password-stdin $(REGISTRY)
	docker tag rabbitos-gateway:$(TAG)      $(REGISTRY)/rabbitos-gateway:$(TAG)
	docker tag rabbitos-orchestrator:$(TAG) $(REGISTRY)/rabbitos-orchestrator:$(TAG)
	docker tag rabbitos-worker:$(TAG)       $(REGISTRY)/rabbitos-worker:$(TAG)
	docker push $(REGISTRY)/rabbitos-gateway:$(TAG)
	docker push $(REGISTRY)/rabbitos-orchestrator:$(TAG)
	docker push $(REGISTRY)/rabbitos-worker:$(TAG)

## ── Helm ──────────────────────────────────────────────────────────────────────
helm-deploy:
	helm upgrade --install rabbitos helm/rabbitos -n $(NS) \
	  --set image.tag=$(TAG) --set global.env=$(ENV) --wait

helm-diff:
	helm diff upgrade rabbitos helm/rabbitos -n $(NS) --set image.tag=$(TAG)

helm-rollback:
	helm rollback rabbitos -n $(NS)

## ── Dev ───────────────────────────────────────────────────────────────────────
dev:
	docker compose -f docker-compose.dev.yml up --build

dev-down:
	docker compose -f docker-compose.dev.yml down -v

## ── Testing ───────────────────────────────────────────────────────────────────
test:
	pytest services/ -v --tb=short

lint:
	ruff check services/
	terraform fmt -check terraform/aws/
	helm lint helm/rabbitos/

## ── Observability ─────────────────────────────────────────────────────────────
logs:
	kubectl logs -n $(NS) -l app=rabbitos-gateway   --tail=100 -f &
	kubectl logs -n $(NS) -l app=rabbitos-orchestrator --tail=100 -f &
	kubectl logs -n $(NS) -l app=rabbitos-worker    --tail=100 -f

status:
	kubectl get pods,svc,hpa -n $(NS)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -f terraform/aws/tfplan
