from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AssetMetadataOut(BaseModel):
    symbol: str
    name: str | None = None
    peg_type: str | None = None


class AssetChainSnapshotOut(BaseModel):
    asset_symbol: str
    asset_name: str | None = None
    chain_name: str
    supply_current: float | None = None
    supply_prev_day: float | None = None
    supply_prev_week: float | None = None
    supply_prev_month: float | None = None
    tvl: float | None = None
    price: float | None = None
    peg_type: str | None = None
    fetched_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceStatusOut(BaseModel):
    source_name: str
    status: str
    last_attempted_fetch: datetime | None = None
    last_successful_fetch: datetime | None = None
    last_error: str | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardResponse(BaseModel):
    asset: AssetMetadataOut
    generated_at: datetime
    refresh_interval_seconds: int
    chains: list[AssetChainSnapshotOut]
    sources: list[SourceStatusOut]


class AssetConfigOut(BaseModel):
    symbol: str
    name: str | None = None
    defillama_symbol: str | None = None
    peg_type: str | None = None
    enabled: bool
    default: bool
