from fastapi import FastAPI
from cashflow_ingest.api.routes_ingest import router as ingest_router
from cashflow_ingest.ingest.pipeline.memory_sink import InMemorySink

app = FastAPI(title="cashflow_ingest", version="0.1.0")

# Global dev sink
app.state.storage = InMemorySink()

app.include_router(ingest_router)

@app.get("/health")
def health():
    return {"ok": True}
