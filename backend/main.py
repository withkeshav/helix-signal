import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import AssetChainSnapshot, SessionLocal, SourceStatus, init_db
from schemas import AssetConfigOut, AssetMetadataOut, DashboardResponse
from signal_engine.core import get_asset_by_symbol, get_default_asset_symbol, load_enabled_assets, refresh_chain_data


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
def dashboard(asset: str | None = None) -> DashboardResponse:
    db = SessionLocal()
    try:
        selected_symbol = (asset or get_default_asset_symbol()).upper()
        selected_asset = get_asset_by_symbol(selected_symbol)
        if selected_asset is None or not bool(selected_asset.get("enabled")):
            raise HTTPException(status_code=404, detail=f"Asset '{selected_symbol}' is not enabled")

        chains = (
            db.query(AssetChainSnapshot)
            .filter(AssetChainSnapshot.asset_symbol == selected_symbol)
            .order_by(AssetChainSnapshot.supply_current.desc(), AssetChainSnapshot.chain_name.asc())
            .all()
        )
        sources = db.query(SourceStatus).order_by(SourceStatus.id.asc()).all()
        latest_snapshot_time = max((chain.fetched_at for chain in chains), default=datetime.now(timezone.utc))
        return DashboardResponse(
            asset=AssetMetadataOut(
                symbol=selected_symbol,
                name=selected_asset.get("name"),
                peg_type=selected_asset.get("peg_type"),
            ),
            generated_at=latest_snapshot_time,
            refresh_interval_seconds=int(os.getenv("REFRESH_INTERVAL_SECONDS", "300")),
            chains=chains,
            sources=sources,
        )
    finally:
        db.close()


@app.get("/api/assets", response_model=list[AssetConfigOut])
def assets() -> list[AssetConfigOut]:
    enabled_assets = load_enabled_assets()
    return [AssetConfigOut(**asset) for asset in enabled_assets]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
