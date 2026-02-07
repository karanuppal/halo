"""Halo API service entrypoint."""

from fastapi import FastAPI

app = FastAPI(title="Halo API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
