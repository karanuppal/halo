"""Halo API service entrypoint."""

from fastapi import FastAPI

from services.api.app.db.init_db import init_db
from services.api.app.routers.command import router as command_router
from services.api.app.routers.order import router as order_router

app = FastAPI(title="Halo API")

app.include_router(order_router)
app.include_router(command_router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
