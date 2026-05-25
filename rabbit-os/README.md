# RabbitOS Phase 1+2 Backend

Lightweight FastAPI backend for the RabbitOS ecosystem.

## Architecture

```
POST /ingest   -> EventBus -> SQLite
POST /analyze  -> AIRouter  -> DeepSeek / Ollama / OpenAI / Mock
GET  /audit    -> in-memory audit log
POST /agents   -> DevAgent | SecurityAgent | ResearchAgent
```

## Quick Start

```bash
cp .env.example .env          # set API keys
pip install -r requirements.txt
uvicorn core.main:app --reload
```

Or with Docker:

```bash
cd docker
docker compose up
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock`, `deepseek`, `openai`, `ollama` |
| `DEEPSEEK_API_KEY` | — | DeepSeek API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL |
| `DB_PATH` | `rabbit_os.db` | SQLite database path |
| `SECRET_KEY` | — | HMAC signing key |
| `DEBUG` | `false` | Enable debug mode |

## API

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/ingest/` | POST | Ingest sensor/spectrum/EEG event |
| `/analyze/` | POST | Route task to LLM provider |
| `/audit/` | GET | Query audit log |
| `/agents/` | GET | List available agents |
| `/agents/` | POST | Run agent command |
| `/docs` | GET | Swagger UI |

## Agents

- **dev** — `review`, `explain`, `generate` code via DeepSeek
- **security** — `assess`, `scan`, `hash` event security risk
- **research** — `query`, `store`, `search` knowledge base
