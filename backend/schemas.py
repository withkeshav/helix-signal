from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetMetadataOut(BaseModel):
    symbol: str
    name: str | None = None
    peg_type: str | None = None


class SupplyMomentumOut(BaseModel):
    day_pct: float | None = None
    week_pct: float | None = None
    month_pct: float | None = None
    day_label: str
    week_label: str
    month_label: str


class ChainSignalOut(BaseModel):
    score: int
    band: str


class DataConfidenceOut(BaseModel):
    score: int
    label: str
    reason: str


class DashboardChainRow(BaseModel):
    asset_symbol: str
    asset_name: str | None = None
    chain_name: str
    supply_current: float | None = None
    supply_prev_day: float | None = None
    supply_prev_week: float | None = None
    supply_prev_month: float | None = None
    chain_tvl: float | None = Field(
        default=None,
        description="Chain-level aggregate stablecoin TVL from DefiLlama stablecoinchains, not asset-specific TVL.",
    )
    price: float | None = None
    peg_type: str | None = None
    fetched_at: datetime
    supply_momentum: SupplyMomentumOut
    chain_share_pct: float | None = None
    chain_signal: ChainSignalOut
    data_confidence: DataConfidenceOut


class SourceStatusOut(BaseModel):
    source_name: str
    status: str
    last_attempted_fetch: datetime | None = None
    last_successful_fetch: datetime | None = None
    last_error: str | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FreshnessOut(BaseModel):
    status: str
    age_seconds: float | None = None
    age_minutes: float | None = None
    basis_timestamp: str | None = None
    basis: str
    fresh_window_seconds: int
    warning_window_seconds: int
    fresh_window_minutes: float
    stale_window_minutes: float
    reason: str


class DepegIndexOut(BaseModel):
    score: int
    current_price: float | None = None
    deviation_abs: float | None = None
    deviation_pct: float | None = None
    peg_status: str
    note: str = "Asset-level price from DefiLlama; not chain-specific oracle precision."


class ChainConcentrationOut(BaseModel):
    top_chain: str | None = None
    top_chain_share_pct: float | None = None
    hhi: float | None = None
    label: str


class AssetSignalOut(BaseModel):
    score: int
    band: str
    components: dict


class DashboardResponse(BaseModel):
    asset: AssetMetadataOut
    generated_at: datetime
    refresh_interval_seconds: int
    freshness: FreshnessOut
    asset_signal: AssetSignalOut
    depeg_index: DepegIndexOut
    chain_concentration: ChainConcentrationOut
    total_supply_current: float | None = None
    total_supply_change_24h_pct: float | None = None
    chains: list[DashboardChainRow]
    sources: list[SourceStatusOut]


class AssetConfigOut(BaseModel):
    symbol: str
    name: str | None = None
    defillama_symbol: str | None = None
    peg_type: str | None = None
    enabled: bool
    default: bool
