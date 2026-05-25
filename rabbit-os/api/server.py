from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import ingest, analyze, audit, agents
from core.config import cfg
from db.sqlite import init_db


def create_app() -> FastAPI:
    app = FastAPI(
        title=cfg.APP_NAME,
        version=cfg.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ingest.router,  prefix="/ingest",  tags=["ingest"])
    app.include_router(analyze.router, prefix="/analyze", tags=["analyze"])
    app.include_router(audit.router,   prefix="/audit",   tags=["audit"])
    app.include_router(agents.router,  prefix="/agents",  tags=["agents"])

    @app.on_event("startup")
    async def startup():
        init_db()

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": cfg.VERSION}

    return app
