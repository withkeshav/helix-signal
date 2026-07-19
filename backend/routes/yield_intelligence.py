"""GET /api/v1/assets/{symbol}/yield, /collateral, /reserve routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import CollateralSnapshot, FiatReserveSnapshot, YieldBearingSnapshot, get_db
from core.api_auth import require_read_open

router = APIRouter()


class YieldBearingSnapshotOut(BaseModel):
    id: int
    asset_symbol: str
    current_apy: float | None = None
    apy_7d_avg: float | None = None
    apy_7d_delta: float | None = None
    yield_source: str | None = None
    yield_sustainability: float | None = None
    funding_rate_current: float | None = None
    funding_rate_7d_avg: float | None = None
    insurance_fund_usd: float | None = None
    insurance_fund_coverage: float | None = None
    staking_ratio: float | None = None
    lending_utilization_pct: float | None = None
    timestamp: str | None = None
    created_at: str | None = None


class CollateralSnapshotOut(BaseModel):
    id: int
    asset_symbol: str
    collateral_ratio: float | None = None
    collateral_assets: dict | None = None
    liquidation_threshold: float | None = None
    liquidation_queue_usd: float | None = None
    debt_ceiling_utilization_pct: float | None = None
    largest_vault_usd: float | None = None
    collateral_health_score: float | None = None
    timestamp: str | None = None
    created_at: str | None = None


class FiatReserveSnapshotOut(BaseModel):
    id: int
    asset_symbol: str
    attestation_date: str | None = None
    reserve_usd: float | None = None
    circulating_supply: float | None = None
    coverage_ratio: float | None = None
    reserve_composition: dict | None = None
    attestation_url: str | None = None
    attestation_source: str | None = None
    attestation_lag_days: int | None = None
    genius_act_compliant: bool | None = None
    mica_status: str | None = None
    created_at: str | None = None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@router.get("/assets/{symbol}/yield", response_model=YieldBearingSnapshotOut, dependencies=[Depends(require_read_open("intelligence:read"))])
def yield_route(symbol: str, db: Session = Depends(get_db)):
    row = db.execute(
        select(YieldBearingSnapshot)
        .where(YieldBearingSnapshot.asset_symbol == symbol.upper())
        .order_by(YieldBearingSnapshot.id.desc())
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No yield data for {symbol}")
    return YieldBearingSnapshotOut(
        id=row.id, asset_symbol=row.asset_symbol,
        current_apy=row.current_apy, apy_7d_avg=row.apy_7d_avg,
        apy_7d_delta=row.apy_7d_delta, yield_source=row.yield_source,
        yield_sustainability=row.yield_sustainability,
        funding_rate_current=row.funding_rate_current,
        funding_rate_7d_avg=row.funding_rate_7d_avg,
        insurance_fund_usd=row.insurance_fund_usd,
        insurance_fund_coverage=row.insurance_fund_coverage,
        staking_ratio=row.staking_ratio,
        lending_utilization_pct=row.lending_utilization_pct,
        timestamp=_iso(row.timestamp), created_at=_iso(row.created_at),
    )


@router.get("/assets/{symbol}/collateral", response_model=CollateralSnapshotOut, dependencies=[Depends(require_read_open("intelligence:read"))])
def collateral_route(symbol: str, db: Session = Depends(get_db)):
    row = db.execute(
        select(CollateralSnapshot)
        .where(CollateralSnapshot.asset_symbol == symbol.upper())
        .order_by(CollateralSnapshot.id.desc())
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No collateral data for {symbol}")
    return CollateralSnapshotOut(
        id=row.id, asset_symbol=row.asset_symbol,
        collateral_ratio=row.collateral_ratio,
        collateral_assets=row.collateral_assets_json,
        liquidation_threshold=row.liquidation_threshold,
        liquidation_queue_usd=row.liquidation_queue_usd,
        debt_ceiling_utilization_pct=row.debt_ceiling_utilization_pct,
        largest_vault_usd=row.largest_vault_usd,
        collateral_health_score=row.collateral_health_score,
        timestamp=_iso(row.timestamp), created_at=_iso(row.created_at),
    )


@router.get("/assets/{symbol}/reserve", response_model=FiatReserveSnapshotOut, dependencies=[Depends(require_read_open("intelligence:read"))])
def reserve_route(symbol: str, db: Session = Depends(get_db)):
    row = db.execute(
        select(FiatReserveSnapshot)
        .where(FiatReserveSnapshot.asset_symbol == symbol.upper())
        .order_by(FiatReserveSnapshot.id.desc())
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No reserve data for {symbol}")
    return FiatReserveSnapshotOut(
        id=row.id, asset_symbol=row.asset_symbol,
        attestation_date=_iso(row.attestation_date),
        reserve_usd=row.reserve_usd, circulating_supply=row.circulating_supply,
        coverage_ratio=row.coverage_ratio,
        reserve_composition=row.reserve_composition,
        attestation_url=row.attestation_url,
        attestation_source=row.attestation_source,
        attestation_lag_days=row.attestation_lag_days,
        genius_act_compliant=row.genius_act_compliant,
        mica_status=row.mica_status, created_at=_iso(row.created_at),
    )