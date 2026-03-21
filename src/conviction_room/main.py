"""FastAPI application entry point for Conviction Room."""

from fastapi import FastAPI

app = FastAPI(
    title="Conviction Room",
    description="Modular plugin architecture for adversarial investment research",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict:
    """System health check endpoint."""
    return {"status": "ok"}
