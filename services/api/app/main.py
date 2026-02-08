"""Halo API service entrypoint."""

from fastapi import FastAPI

from services.api.app.routers.order import router as order_router

app = FastAPI(title="Halo API")

app.include_router(order_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
