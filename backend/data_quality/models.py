"""Data quality models and schemas."""

from typing import Dict
from pydantic import BaseModel

class DataQualityStats(BaseModel):
    """Overall data quality statistics."""
    overall_score: float
    source_health_score: float
    asset_completeness_score: float
    consistency_score: float
    freshness_score: float

class SourceQualityMetrics(BaseModel):
    """Metrics for data source quality."""
    total_sources: int
    healthy_sources: int
    degraded_sources: int
    down_sources: int
    sources_by_status: Dict[str, int]

class DataQualityReport(BaseModel):
    """Complete data quality report."""
    generated_at: str
    overall_quality: DataQualityStats
    source_quality: SourceQualityMetrics