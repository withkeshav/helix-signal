from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChainDataOut(BaseModel):
    chain_name: str
    usdt_supply: float
    usdt_supply_prev_day: float | None = None
    usdt_supply_prev_week: float | None = None
    usdt_supply_prev_month: float | None = None
    tvl: float | None = None
    price: float | None = None
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
    generated_at: datetime
    chains: list[ChainDataOut]
    sources: list[SourceStatusOut]
