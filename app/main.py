from fastapi import FastAPI


app = FastAPI(
    title="Buyvora Agent",
    description="A personal e-commerce agent project.",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return a small liveness response for local development and deployment."""
    return {"status": "ok", "service": "buyvora-agent"}

