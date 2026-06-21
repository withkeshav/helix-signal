#!/usr/bin/env python3
"""
Script to monitor API rate limits and system performance for Helix Signal.
"""

import sqlite3
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

def get_database_path() -> str:
    """Find the database file."""
    possible_paths = [
        "backend/helix.db",
        "helix.db",
        "data/helix.db",
        "/app/backend/helix.db",
        "/app/helix.db"
    ]
    
    for path in possible_paths:
        if Path(path).exists():
            return path
    
    # Try to find in Docker container
    docker_paths = [
        "/data/helix.db",
        "/app/data/helix.db"
    ]
    
    for path in docker_paths:
        if Path(path).exists():
            return path
    
    raise FileNotFoundError(f"Database file not found. Tried paths: {possible_paths + docker_paths}")

def get_rate_limit_usage() -> dict:
    """Get current rate limit usage from the database."""
    try:
        db_path = get_database_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get today's date
        today = date.today().isoformat()
        
        # Query source usage for today
        cursor.execute("""
            SELECT source_name, call_count 
            FROM source_usage 
            WHERE usage_date = ?
        """, (today,))
        
        usage = cursor.fetchall()
        conn.close()
        
        return {source: count for source, count in usage}
    except Exception as e:
        print(f"Error reading database: {e}")
        return {}

def get_system_performance() -> dict:
    """Get system performance metrics."""
    try:
        db_path = get_database_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get recent source statuses
        cursor.execute("""
            SELECT source_name, status, last_successful_fetch, last_error
            FROM source_status
            ORDER BY updated_at DESC
            LIMIT 10
        """)
        
        statuses = cursor.fetchall()
        
        # Get recent asset freshness
        cursor.execute("""
            SELECT asset_symbol, last_successful_fetch
            FROM asset_freshness
            ORDER BY updated_at DESC
            LIMIT 10
        """)
        
        freshness = cursor.fetchall()
        
        # Get recent events count
        cursor.execute("""
            SELECT COUNT(*) as event_count
            FROM signal_events
            WHERE timestamp > datetime('now', '-1 hour')
        """)
        
        event_result = cursor.fetchone()
        event_count = event_result[0] if event_result else 0
        
        conn.close()
        
        return {
            "statuses": statuses,
            "freshness": freshness,
            "recent_events": event_count
        }
    except Exception as e:
        print(f"Error reading performance metrics: {e}")
        return {}

def check_rate_limits(usage: dict) -> list:
    """Check if any sources are approaching rate limits."""
    # Rate limits (requests per minute)
    rate_limits = {
        "dexscreener": 120,
        "coingecko": 100,
        "defillama": 1000,  # Higher limit for defillama
    }
    
    alerts = []
    
    for source, count in usage.items():
        if source in rate_limits:
            limit = rate_limits[source]
            usage_percent = (count / limit) * 100
            
            if usage_percent > 90:
                alerts.append({
                    "source": source,
                    "count": count,
                    "limit": limit,
                    "percent": usage_percent,
                    "severity": "CRITICAL"
                })
            elif usage_percent > 80:
                alerts.append({
                    "source": source,
                    "count": count,
                    "limit": limit,
                    "percent": usage_percent,
                    "severity": "WARNING"
                })
    
    return alerts

def main():
    """Main function to monitor rate limits and system performance."""
    # Get current usage
    usage = get_rate_limit_usage()
    
    # Get system performance
    performance = get_system_performance()
    
    # Check rate limits
    alerts = check_rate_limits(usage)
    
    # Print results
    print(f"Rate Limit & Performance Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    if usage:
        print("API Usage:")
        for source, count in usage.items():
            limit = {"dexscreener": 120, "coingecko": 100, "defillama": 1000}.get(source, 1000)
            percent = (count / limit) * 100
            status = "⚠️ " if percent > 80 else "✅"
            print(f"{status} {source:12}: {count:4d}/{limit:4d} ({percent:5.1f}%)")
    else:
        print("No usage data found")
    
    if performance:
        print("\nSystem Performance:")
        print(f"Recent Events (last hour): {performance.get('recent_events', 0)}")
        
        print("\nSource Status:")
        for status in performance.get('statuses', []):
            source_name, status_val, last_fetch, last_error = status
            if last_fetch:
                # Calculate age of last fetch
                try:
                    last_fetch_dt = datetime.fromisoformat(last_fetch.replace('Z', '+00:00'))
                    age_minutes = (datetime.now(last_fetch_dt.tzinfo) - last_fetch_dt).total_seconds() / 60
                    age_str = f"{age_minutes:.1f}m ago"
                except:
                    age_str = "unknown"
                print(f"  {source_name:12}: {status_val:8} (last: {age_str})")
            else:
                print(f"  {source_name:12}: {status_val:8}")
    
    # Print alerts
    if alerts:
        print("\n⚠️  ALERTS:")
        for alert in alerts:
            print(f"{alert['severity']}: {alert['source']} at {alert['count']}/{alert['limit']} calls ({alert['percent']:.1f}%)")

if __name__ == "__main__":
    main()