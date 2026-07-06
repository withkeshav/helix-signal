"""GET /api/v1/assets/{symbol}/yield, /collateral, /reserve routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import FiatReserveSnapshot, CollateralSnapshot, YieldBearingSnapshot, get_db

router = APIRouter()


class YieldBearingSnapshotOut(BaseModel):
    id: int
    asset_symbol: str
    current_apy: float | None = None
    yield_source: str | None = None
    total_supply: float | None = None
    timestamp: str | None = None


class CollateralSnapshotOut(BaseModel):
    id: int
    asset_symbol: str
    collateral_ratio: float | None = None
    total_collateral_usd: float | None = None
    total_debt_usd: float | None = None
    recovery_mode: bool | None = None
    timestamp: str | None = None


class FiatReserveSnapshotOut(BaseModel):
    id: int
    asset_symbol: str
    reserve_usd: float | None = None
    circulating_supply: float | None = None
    coverage_ratio: float | None = None
    attestation_date: str | None = None
    timestamp: str | None = None


@router.get("/assets/{symbol}/yield", response_model=YieldBearingSnapshotOut)
def yield_route(symbol: str, db: Session = Depends(get_db)):
    row = db.query(YieldBearingSnapshot).filter(
        YieldBearingSnapshot.asset_symbol == symbol.upper()
    ).order_by(YieldBearingSnapshot.id.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No yield data for {symbol}")
    return YieldBearingSnapshotOut(
        id=row.id, asset_symbol=row.asset_symbol,
        current_apy=row.current_apy, yield_source=row.yield_source,
        total_supply=row.total_supply,
        timestamp=row.timestamp.isoformat() if row.timestamp else None,
    )


@router.get("/assets/{symbol}/collateral", response_model=CollateralSnapshotOut)
def collateral_route(symbol: str, db: Session = Depends(get_db)):
    row = db.query(CollateralSnapshot).filter(
        CollateralSnapshot.asset_symbol == symbol.upper()
    ).order_by(CollateralSnapshot.id.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No collateral data for {symbol}")
    return CollateralSnapshotOut(
        id=row.id, asset_symbol=row.asset_symbol,
        collateral_ratio=row.collateral_ratio,
        total_collateral_usd=row.total_collateral_usd,
        total_debt_usd=row.total_debt_usd,
        recovery_mode=row.recovery_mode,
        timestamp=row.timestamp.isoformat() if row.timestamp else None,
    )


@router.get("/assets/{symbol}/reserve", response_model=FiatReserveSnapshotOut)
def reserve_route(symbol: str, db: Session = Depends(get_db)):
    row = db.query(FiatReserveSnapshot).filter(
        FiatReserveSnapshot.asset_symbol == symbol.upper()
    ).order_by(FiatReserveSnapshot.id.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No reserve data for {symbol}")
    return FiatReserveSnapshotOut(
        id=row.id, asset_symbol=row.asset_symbol,
        reserve_usd=row.reserve_usd,
        circulating_supply=row.circulating_supply,
        coverage_ratio=row.coverage_ratio,
        attestation_date=row.attestation_date.isoformat() if row.attestation_date else None,
        timestamp=row.created_at.isoformat() if hasattr(row, 'created_at') and row.created_at else None,
    )
