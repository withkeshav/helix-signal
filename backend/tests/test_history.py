from datetime import datetime, timezone

from signal_engine.history import BUCKET_SECONDS, EVENT_DEDUP_MINUTES, _depeg_zone


def test_bucket_id_five_minute_alignment():
    ts = datetime(2026, 1, 1, 12, 7, 30, tzinfo=timezone.utc)
    bucket_id = int(ts.timestamp() // BUCKET_SECONDS)
    assert bucket_id * BUCKET_SECONDS <= ts.timestamp() < (bucket_id + 1) * BUCKET_SECONDS


def test_depeg_zones():
    assert _depeg_zone(10) == "low"
    assert _depeg_zone(50) == "mid"
    assert _depeg_zone(80) == "high"


def test_event_dedup_window_positive():
    assert EVENT_DEDUP_MINUTES == 30
