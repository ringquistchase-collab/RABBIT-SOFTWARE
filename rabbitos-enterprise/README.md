# RabbitOS Enterprise AI Platform

Production-grade AI cloud platform for the RabbitOS ecosystem.
Deploys on AWS EKS with Kafka task routing, Qdrant vector memory,
Neo4j knowledge graph, and multi-provider LLM inference.

## Architecture

```
Client
  └── Gateway (FastAPI, JWT, WebSocket)
        └── AI Orchestrator (session mgmt, Kafka producer)
              └── AI Workers (Kafka consumer, LLM inference)
                    ├── Vector Memory (Qdrant)
                    ├── Graph Memory  (Neo4j)
                    └── Cold Storage  (S3)

Ingest Bridge ──────────────────────────────> Kafka
  (Supabase sensor/spectrum → enterprise pipeline)

Observability: Prometheus + Grafana
```

## Quick Start

```bash
cp .env.example .env          # fill in AWS_ACCOUNT_ID, API keys
./bootstrap.sh dev            # provision infra + deploy charts
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| gateway | 8080 | JWT auth, rate limiting, WebSocket |
| ai-orchestrator | 8081 | Session management, task routing |
| ai-workers | — | Kafka consumer, LLM inference |
| ingest | 8082 | Supabase → Kafka bridge |

## LLM Providers

Set `LLM_PROVIDER` in `.env`:
- `deepseek` — DeepSeek API (requires `DEEPSEEK_API_KEY`)
- `openai`   — OpenAI API (requires `OPENAI_API_KEY`)
- `mock`     — Deterministic mock (no API key needed)

## Development

```bash
make dev        # docker compose local stack
make test       # pytest
make lint       # ruff + terraform fmt + helm lint
make build TAG=local   # build docker images
```

## Deploy

```bash
make deploy ENV=staging TAG=$(git rev-parse --short HEAD)
```

GitHub Actions runs lint → test → build → deploy on every push to `main`.
