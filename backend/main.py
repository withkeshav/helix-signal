import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import AssetChainSnapshot, SessionLocal, SourceStatus, init_db
from schemas import (
    AssetConfigOut,
    AssetMetadataOut,
    AssetSignalOut,
    ChainConcentrationOut,
    ChainSignalOut,
    DashboardChainRow,
    DashboardResponse,
    DataConfidenceOut,
    DepegIndexOut,
    FreshnessOut,
    SourceStatusOut,
    SupplyMomentumOut,
)
from signal_engine import scoring
from signal_engine.core import get_asset_by_symbol, get_default_asset_symbol, load_enabled_assets, refresh_chain_data


def _refresh_job() -> None:
    db = SessionLocal()
    try:
        refresh_chain_data(db)
    finally:
        db.close()


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


@app.post("/api/refresh")
def api_refresh() -> dict[str, bool]:
    """Run the DefiLlama ingest pipeline once (same as the scheduler job)."""
    db = SessionLocal()
    try:
        refresh_chain_data(db)
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard(asset: str | None = None) -> DashboardResponse:
    db = SessionLocal()
    try:
        selected_symbol = (asset or get_default_asset_symbol()).upper()
        selected_asset = get_asset_by_symbol(selected_symbol)
        if selected_asset is None or not bool(selected_asset.get("enabled")):
            raise HTTPException(status_code=404, detail=f"Asset '{selected_symbol}' is not enabled")

        refresh_interval = int(os.getenv("REFRESH_INTERVAL_SECONDS", "300"))

        chains_orm = (
            db.query(AssetChainSnapshot)
            .filter(AssetChainSnapshot.asset_symbol == selected_symbol)
            .order_by(AssetChainSnapshot.supply_current.desc(), AssetChainSnapshot.chain_name.asc())
            .all()
        )
        sources_orm = db.query(SourceStatus).order_by(SourceStatus.id.asc()).all()
        sources = [SourceStatusOut.model_validate(s) for s in sources_orm]

        defillama = next((s for s in sources_orm if s.source_name == "defillama"), None)
        source_status = defillama.status if defillama else "unknown"

        newest_chain_snapshot = max((_utc(c.fetched_at) for c in chains_orm), default=None) if chains_orm else None

        freshness_dict = scoring.compute_freshness(
            source_status=source_status,
            last_successful_fetch=_utc(defillama.last_successful_fetch) if defillama else None,
            newest_chain_snapshot=newest_chain_snapshot,
            refresh_interval_seconds=refresh_interval,
        )
        freshness = FreshnessOut(**freshness_dict)

        raw_total = sum((c.supply_current or 0.0) for c in chains_orm)
        total_supply = raw_total if raw_total > 0 else None

        total_prev_day = sum((c.supply_prev_day or 0.0) for c in chains_orm)
        total_prev_week = sum((c.supply_prev_week or 0.0) for c in chains_orm)
        total_prev_month = sum((c.supply_prev_month or 0.0) for c in chains_orm)

        total_change_24h_pct: float | None = None
        if total_supply is not None and total_prev_day > 0:
            total_change_24h_pct = ((total_supply - total_prev_day) / total_prev_day) * 100.0

        chain_shares: list[float] = []
        if total_supply and total_supply > 0:
            for c in chains_orm:
                if c.supply_current is not None and c.supply_current > 0:
                    chain_shares.append(float(c.supply_current) / float(total_supply))

        source_ok = defillama is not None and defillama.status == "ok"
        source_error = defillama.last_error if defillama else None

        price = next((c.price for c in chains_orm if c.price is not None), None)

        if price is not None:
            dev_abs, dev_pct = scoring.peg_deviation(price)
        else:
            dev_abs, dev_pct = None, None
        depeg_index = DepegIndexOut(
            score=scoring.depeg_index_score(price),
            current_price=price,
            deviation_abs=dev_abs,
            deviation_pct=dev_pct,
            peg_status=scoring.peg_status_label(price),
        )

        conc_s, conc_detail = scoring.concentration_component(chain_shares)
        top_chain_name: str | None = None
        if total_supply and total_supply > 0 and chains_orm:
            top_row = max(chains_orm, key=lambda c: (c.supply_current or 0.0))
            if (top_row.supply_current or 0.0) > 0:
                top_chain_name = top_row.chain_name

        chain_concentration = ChainConcentrationOut(
            top_chain=top_chain_name,
            top_chain_share_pct=conc_detail.get("top_chain_share_pct"),
            hhi=conc_detail.get("hhi"),
            label=scoring.composite_band(conc_s),
        )

        asset_signal_dict = scoring.compute_asset_signal(
            price=price,
            supply_current=float(total_supply or 0.0),
            supply_prev_day=total_prev_day if total_prev_day > 0 else None,
            supply_prev_week=total_prev_week if total_prev_week > 0 else None,
            supply_prev_month=total_prev_month if total_prev_month > 0 else None,
            chain_shares=chain_shares,
            source_ok=source_ok,
            source_error=source_error,
            age_seconds=freshness_dict.get("age_seconds"),
            refresh_interval_seconds=refresh_interval,
        )
        asset_signal = AssetSignalOut(
            score=int(asset_signal_dict["score"]),
            band=str(asset_signal_dict["band"]),
            components=dict(asset_signal_dict["components"]),
        )

        now = datetime.now(timezone.utc)
        dashboard_chains: list[DashboardChainRow] = []
        asset_name = selected_asset.get("name")

        for c in chains_orm:
            fetched = _utc(c.fetched_at)
            age_s = (now - fetched).total_seconds() if fetched else None

            sm_raw = scoring.chain_supply_momentum(
                supply_current=c.supply_current,
                supply_prev_day=c.supply_prev_day,
                supply_prev_week=c.supply_prev_week,
                supply_prev_month=c.supply_prev_month,
            )
            supply_momentum = SupplyMomentumOut(**sm_raw)

            share_pct = (
                (float(c.supply_current) / float(total_supply)) * 100.0
                if total_supply and c.supply_current is not None and total_supply > 0
                else None
            )

            cur_supply = float(c.supply_current or 0.0)
            mom_hint, _ = scoring.supply_momentum_component(
                supply_current=cur_supply,
                supply_prev_day=c.supply_prev_day,
                supply_prev_week=c.supply_prev_week,
                supply_prev_month=c.supply_prev_month,
            )

            cs_raw = scoring.chain_row_signal(
                chain_share_pct=share_pct,
                peg_price=c.price,
                momentum_score_hint=mom_hint,
            )
            chain_signal = ChainSignalOut(score=int(cs_raw["score"]), band=str(cs_raw["band"]))

            dc_raw = scoring.chain_data_confidence(
                source_ok=source_ok,
                chain_snapshot_age_seconds=age_s,
                refresh_interval_seconds=refresh_interval,
            )
            data_confidence = DataConfidenceOut(
                score=int(dc_raw["score"]),
                label=str(dc_raw["label"]),
                reason=str(dc_raw["reason"]),
            )

            dashboard_chains.append(
                DashboardChainRow(
                    asset_symbol=selected_symbol,
                    asset_name=asset_name,
                    chain_name=c.chain_name,
                    supply_current=c.supply_current,
                    supply_prev_day=c.supply_prev_day,
                    supply_prev_week=c.supply_prev_week,
                    supply_prev_month=c.supply_prev_month,
                    chain_tvl=c.tvl,
                    price=c.price,
                    peg_type=c.peg_type,
                    fetched_at=c.fetched_at,
                    supply_momentum=supply_momentum,
                    chain_share_pct=round(share_pct, 4) if share_pct is not None else None,
                    chain_signal=chain_signal,
                    data_confidence=data_confidence,
                )
            )

        generated_at = datetime.now(timezone.utc)

        return DashboardResponse(
            asset=AssetMetadataOut(
                symbol=selected_symbol,
                name=selected_asset.get("name"),
                peg_type=selected_asset.get("peg_type"),
            ),
            generated_at=generated_at,
            refresh_interval_seconds=refresh_interval,
            freshness=freshness,
            asset_signal=asset_signal,
            depeg_index=depeg_index,
            chain_concentration=chain_concentration,
            total_supply_current=total_supply,
            total_supply_change_24h_pct=total_change_24h_pct,
            chains=dashboard_chains,
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
