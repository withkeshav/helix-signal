from datetime import datetime
from typing import Any

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
    price_coingecko: float | None = None
    price_dexscreener: float | None = None
    market_cap: float | None = None
    volume_24h: float | None = None
    total_liquidity_usd: float | None = None
    top3_pool_share_pct: float | None = None
    pool_count: int | None = None
    peg_type: str | None = None
    fetched_at: datetime
    supply_momentum: SupplyMomentumOut
    chain_share_pct: float | None = None
    chain_signal: ChainSignalOut
    data_confidence: DataConfidenceOut


class SourceStatusOut(BaseModel):
    source_name: str
    status: str
    previous_status: str | None = None
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


class DataQualityOut(BaseModel):
    degraded_sources: list[str] = []
    using_cached_data: bool = False
    nlp_available: bool = False


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
    data_quality: DataQualityOut = DataQualityOut()


class AssetConfigOut(BaseModel):
    symbol: str
    name: str | None = None
    defillama_symbol: str | None = None
    peg_type: str | None = None
    enabled: bool
    default: bool


# --- V2.4 trends and events ---


class TrendPointOut(BaseModel):
    timestamp: datetime
    total_supply: float | None = None
    price: float | None = None
    depeg_index: int
    signal_score: int
    signal_band: str
    concentration_score: int
    data_confidence: str = Field(description="Aggregate label: High, Medium, or Low.")


class TrendSummaryOut(BaseModel):
    point_count: int
    supply_change_abs: float | None = None
    supply_change_pct: float | None = None
    score_change: float | None = None
    max_depeg_index: int | None = None
    latest_band: str | None = None
    selected_window: str = Field(description="Requested window token, e.g. 24h, 7d, 30d.")
    window_span_hours: float = Field(description="Width of the selected window in hours.")
    first_timestamp: datetime | None = None
    latest_timestamp: datetime | None = None
    available_duration_minutes: float | None = Field(
        default=None,
        description="Span from first to last returned point, minutes.",
    )
    low_data: bool = Field(description="True when coverage of the window is short or points are sparse.")
    low_data_reason: str | None = Field(
        default=None,
        description="Human-readable explanation for operators when low_data is true.",
    )
    chart_axis_min_utc: datetime | None = Field(
        default=None,
        description="Suggested chart x-axis minimum (UTC) for the full selected window.",
    )
    chart_axis_max_utc: datetime | None = Field(
        default=None,
        description="Suggested chart x-axis maximum (UTC), typically now.",
    )


class TrendResponseOut(BaseModel):
    asset: str
    window: str
    generated_at: datetime
    points: list[TrendPointOut]
    summary: TrendSummaryOut


class ChainTrendPointOut(BaseModel):
    timestamp: datetime
    supply: float | None = None
    supply_share_pct: float | None = None
    chain_tvl: float | None = None
    chain_signal_score: int
    chain_signal_band: str
    data_confidence_score: int


class ChainTrendSeriesOut(BaseModel):
    chain_key: str
    chain_name: str
    points: list[ChainTrendPointOut]


class ChainTrendResponseOut(BaseModel):
    asset: str
    window: str
    generated_at: datetime
    series: list[ChainTrendSeriesOut]
    summary: dict[str, Any]


class SignalEventOut(BaseModel):
    id: int
    asset_symbol: str
    chain_key: str | None = None
    event_type: str
    severity: str
    title: str
    summary: str
    old_value: str | None = None
    new_value: str | None = None
    delta: str | None = None
    threshold: str | None = None
    timestamp: datetime
    metadata: dict | None = None


class SignalEventsResponseOut(BaseModel):
    generated_at: datetime
    events: list[SignalEventOut]
