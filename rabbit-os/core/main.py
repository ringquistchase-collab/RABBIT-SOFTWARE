"""
RabbitOS Phase 1+2 — entry point.
Run:  uvicorn core.main:app --reload
"""
from core.config import cfg
from api.server import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("core.main:app", host=cfg.HOST, port=cfg.PORT, reload=cfg.DEBUG)
