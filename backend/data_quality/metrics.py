"""Data quality metrics collection and analysis."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session

from database import (
    SourceStatus, AssetChainSnapshot, AssetFreshness, 
    SourceUsage, AiUsage, SettingsAuditLog
)
from providers.settings import get_setting

# Configure logging
logger = logging.getLogger(__name__)

class DataQualityMetrics:
    """Collect and analyze data quality metrics."""
    
    @staticmethod
    def get_source_quality_metrics(db: Session) -> Dict[str, Any]:
        """Get quality metrics for all data sources."""
        try:
            sources = db.query(SourceStatus).all()
            metrics = {
                "total_sources": len(sources),
                "healthy_sources": 0,
                "degraded_sources": 0,
                "down_sources": 0,
                "sources_by_status": {},
                "completeness_by_source": {},
                "freshness_by_source": {},
                "error_rates": {}
            }
            
            for source in sources:
                status = source.status.lower()
                metrics["sources_by_status"][status] = metrics["sources_by_status"].get(status, 0) + 1
                
                if status == "ok":
                    metrics["healthy_sources"] += 1
                elif status == "degraded":
                    metrics["degraded_sources"] += 1
                else:
                    metrics["down_sources"] += 1
                
                # Calculate completeness - successful vs attempted fetches
                if source.last_attempted_fetch and source.last_successful_fetch:
                    time_diff = source.last_attempted_fetch - source.last_successful_fetch
                    hours_since_success = time_diff.total_seconds() / 3600
                    # Completeness score (higher is better)
                    completeness = max(0, 100 - (hours_since_success * 2))  # Simple decay model
                    metrics["completeness_by_source"][source.source_name] = round(completeness, 2)
                
                # Calculate freshness
                if source.last_successful_fetch:
                    freshness_hours = (datetime.utcnow() - source.last_successful_fetch).total_seconds() / 3600
                    metrics["freshness_by_source"][source.source_name] = round(freshness_hours, 2)
                
                # Error rates from last error field
                if source.last_error:
                    metrics["error_rates"][source.source_name] = "Has recent errors"
                else:
                    metrics["error_rates"][source.source_name] = "No recent errors"
            
            return metrics
        except Exception as e:
            logger.error(f"Error getting source quality metrics: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def get_asset_data_quality(db: Session, asset_symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get data quality metrics for asset data."""
        try:
            query = db.query(AssetChainSnapshot)
            if asset_symbol:
                query = query.filter(AssetChainSnapshot.asset_symbol == asset_symbol.upper())
            
            snapshots = query.all()
            
            metrics = {
                "total_snapshots": len(snapshots),
                "assets_tracked": len(set(s.chain_name for s in snapshots)),
                "chains_tracked": len(set(s.chain_name for s in snapshots)),
                "completeness_by_asset": {},
                "data_gaps": [],
                "consistency_metrics": {}
            }
            
            # Group by asset
            asset_snapshots = {}
            for snapshot in snapshots:
                key = snapshot.asset_symbol
                if key not in asset_snapshots:
                    asset_snapshots[key] = []
                asset_snapshots[key].append(snapshot)
            
            # Calculate completeness for each asset
            for asset, snapshots_list in asset_snapshots.items():
                if snapshots_list:
                    # Calculate data completeness based on expected refresh intervals
                    freshness = db.query(AssetFreshness).filter(
                        AssetFreshness.asset_symbol == asset
                    ).first()
                    
                    if freshness and freshness.last_successful_fetch:
                        age_hours = (datetime.utcnow() - freshness.last_successful_fetch).total_seconds() / 3600
                        # Simple completeness score (newer = better)
                        completeness = max(0, 100 - (age_hours * 5))  # 5% penalty per hour of staleness
                        metrics["completeness_by_asset"][asset] = round(completeness, 2)
                    
                    # Check for data gaps (missing recent snapshots)
                    if len(snapshots_list) > 1:
                        latest = max(snapshots_list, key=lambda s: s.fetched_at)
                        earliest = min(snapshots_list, key=lambda s: s.fetched_at)
                        expected_count = (latest.fetched_at - earliest.fetched_at).total_seconds() / 300  # 5 min intervals
                        actual_count = len(snapshots_list)
                        gap_ratio = max(0, (expected_count - actual_count) / expected_count * 100) if expected_count > 0 else 0
                        if gap_ratio > 10:  # More than 10% gaps
                            metrics["data_gaps"].append({
                                "asset": asset,
                                "gap_percentage": round(gap_ratio, 2),
                                "note": f"{gap_ratio:.1f}% data points missing"
                            })
            
            return metrics
        except Exception as e:
            logger.error(f"Error getting asset data quality metrics: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def get_usage_metrics(db: Session) -> Dict[str, Any]:
        """Get API usage and performance metrics."""
        try:
            # Get source usage for the last day
            yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            source_usage = db.query(SourceUsage).filter(
                SourceUsage.usage_date == yesterday
            ).all()
            
            # Get AI usage for the last day
            ai_usage = db.query(AiUsage).filter(
                AiUsage.usage_date == yesterday
            ).all()
            
            metrics = {
                "source_usage": {},
                "ai_usage": {},
                "total_api_calls": 0,
                "total_ai_tokens": 0,
                "performance_metrics": {}
            }
            
            # Calculate source usage metrics
            total_source_calls = 0
            for usage in source_usage:
                metrics["source_usage"][usage.source_name] = {
                    "calls": usage.call_count,
                    "last_call": usage.last_call_at.isoformat() if usage.last_call_at else None
                }
                total_source_calls += usage.call_count
            
            metrics["total_api_calls"] = total_source_calls
            
            # Calculate AI usage metrics
            total_ai_tokens = 0
            for usage in ai_usage:
                metrics["ai_usage"][f"{usage.provider}_{usage.model}"] = {
                    "tokens": usage.tokens,
                    "calls": usage.calls,
                    "estimated_cost": usage.estimated_cost
                }
                total_ai_tokens += usage.tokens
            
            metrics["total_ai_tokens"] = total_ai_tokens
            
            # Performance metrics based on rate limiting
            from core.limiter import limiter
            if hasattr(limiter, '_window_stats'):
                metrics["performance_metrics"]["rate_limit_stats"] = limiter._window_stats
            
            return metrics
        except Exception as e:
            logger.error(f"Error getting usage metrics: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def get_consistency_metrics(db: Session) -> Dict[str, Any]:
        """Get data consistency and validation metrics."""
        try:
            # Check for cross-source discrepancies
            discrepancies = []
            
            # Get recent asset chain snapshots to check consistency
            recent_snapshots = db.query(AssetChainSnapshot).order_by(
                AssetChainSnapshot.fetched_at.desc()
            ).limit(100).all()
            
            # Group by asset and timestamp to check cross-source consistency
            asset_timestamp_data = {}
            for snapshot in recent_snapshots:
                key = (snapshot.asset_symbol, snapshot.fetched_at.strftime("%Y-%m-%d %H:%M"))
                if key not in asset_timestamp_data:
                    asset_timestamp_data[key] = []
                asset_timestamp_data[key].append(snapshot)
            
            # Check for significant price discrepancies
            for (asset, timestamp), snapshots in asset_timestamp_data.items():
                if len(snapshots) > 1:
                    prices = [s.price for s in snapshots if s.price is not None]
                    if len(prices) > 1:
                        avg_price = sum(prices) / len(prices)
                        max_diff = max(abs(p - avg_price) for p in prices)
                        if avg_price > 0:
                            diff_pct = (max_diff / avg_price) * 100
                            if diff_pct > 1.0:  # More than 1% difference
                                discrepancies.append({
                                    "asset": asset,
                                    "timestamp": timestamp,
                                    "discrepancy_pct": round(diff_pct, 2),
                                    "sources_count": len(snapshots),
                                    "note": f"Price discrepancy of {diff_pct:.2f}% between sources"
                                })
            
            metrics = {
                "total_discrepancies": len(discrepancies),
                "top_discrepancies": discrepancies[:10],  # Top 10 discrepancies
                "cross_source_validation": {
                    "total_checks": len(asset_timestamp_data),
                    "failed_validations": len(discrepancies)
                }
            }
            
            # Add audit trail health
            recent_audits = db.query(SettingsAuditLog).order_by(
                SettingsAuditLog.created_at.desc()
            ).limit(50).all()
            
            metrics["audit_trail"] = {
                "total_changes": len(recent_audits),
                "recent_changes": len([a for a in recent_audits 
                                     if a.created_at > datetime.utcnow() - timedelta(hours=24)])
            }
            
            return metrics
        except Exception as e:
            logger.error(f"Error getting consistency metrics: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def get_overall_data_quality_score(db: Session) -> Dict[str, Any]:
        """Calculate overall data quality score."""
        try:
            source_metrics = DataQualityMetrics.get_source_quality_metrics(db)
            asset_metrics = DataQualityMetrics.get_asset_data_quality(db)
            usage_metrics = DataQualityMetrics.get_usage_metrics(db)
            consistency_metrics = DataQualityMetrics.get_consistency_metrics(db)
            
            # Calculate weighted score based on key metrics
            scores = []
            
            # Source health contributes 30%
            if "healthy_sources" in source_metrics and "total_sources" in source_metrics:
                source_health_score = (source_metrics["healthy_sources"] / 
                                     max(1, source_metrics["total_sources"])) * 100
                scores.append(source_health_score * 0.30)
            
            # Asset completeness contributes 25%
            if "completeness_by_asset" in asset_metrics:
                avg_completeness = 0
                if asset_metrics["completeness_by_asset"]:
                    avg_completeness = sum(asset_metrics["completeness_by_asset"].values()) / len(asset_metrics["completeness_by_asset"])
                scores.append(avg_completeness * 0.25)
            
            # Consistency contributes 25%
            if "cross_source_validation" in consistency_metrics:
                validation = consistency_metrics["cross_source_validation"]
                if validation["total_checks"] > 0:
                    consistency_score = (1 - (validation["failed_validations"] / validation["total_checks"])) * 100
                    scores.append(consistency_score * 0.25)
            
            # Freshness contributes 20%
            if "freshness_by_source" in source_metrics:
                fresh_sources = [h for h in source_metrics["freshness_by_source"].values() if h < 2]  # < 2 hours old
                freshness_score = (len(fresh_sources) / max(1, len(source_metrics["freshness_by_source"]))) * 100
                scores.append(freshness_score * 0.20)
            
            overall_score = sum(scores) if scores else 0
            
            return {
                "overall_score": round(overall_score, 2),
                "source_health_score": round(source_health_score, 2) if 'source_health_score' in locals() else 0,
                "asset_completeness_score": round(avg_completeness, 2) if 'avg_completeness' in locals() else 0,
                "consistency_score": round(consistency_score, 2) if 'consistency_score' in locals() else 0,
                "freshness_score": round(freshness_score, 2) if 'freshness_score' in locals() else 0,
                "components": {
                    "source_quality": source_metrics,
                    "asset_quality": asset_metrics,
                    "usage_metrics": usage_metrics,
                    "consistency_metrics": consistency_metrics
                }
            }
        except Exception as e:
            logger.error(f"Error calculating overall data quality score: {e}")
            return {"error": str(e), "overall_score": 0}

# Convenience functions
def get_all_data_quality_metrics(db: Session) -> Dict[str, Any]:
    """Get comprehensive data quality metrics."""
    return DataQualityMetrics.get_overall_data_quality_score(db)

def get_data_quality_report(db: Session) -> Dict[str, Any]:
    """Generate a complete data quality report."""
    try:
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "overall_quality": DataQualityMetrics.get_overall_data_quality_score(db),
            "source_quality": DataQualityMetrics.get_source_quality_metrics(db),
            "asset_quality": DataQualityMetrics.get_asset_data_quality(db),
            "usage_metrics": DataQualityMetrics.get_usage_metrics(db),
            "consistency_metrics": DataQualityMetrics.get_consistency_metrics(db)
        }
        return report
    except Exception as e:
        logger.error(f"Error generating data quality report: {e}")
        return {"error": str(e), "generated_at": datetime.utcnow().isoformat()}