import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import ChainData, SessionLocal, SourceStatus, init_db
from schemas import DashboardResponse
from signal_engine.core import refresh_chain_data


def _refresh_job() -> None:
    db = SessionLocal()
    try:
        refresh_chain_data(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()

    scheduler = BackgroundScheduler()
    interval_seconds = int(os.getenv("REFRESH_INTERVAL_SECONDS", "300"))
    scheduler.add_job(_refresh_job, "interval", seconds=interval_seconds, id="defillama-refresh", replace_existing=True)
    scheduler.start()

    # Trigger one immediate refresh at startup.
    _refresh_job()

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Helix-Signal API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> str:
    return "Hello Helix-Signal!"


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard() -> DashboardResponse:
    db = SessionLocal()
    try:
        chains = db.query(ChainData).order_by(ChainData.id.asc()).all()
        sources = db.query(SourceStatus).order_by(SourceStatus.id.asc()).all()
        return DashboardResponse(
            generated_at=datetime.now(timezone.utc),
            chains=chains,
            sources=sources,
        )
    finally:
        db.close()
