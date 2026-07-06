"""Tests for DEWS and depeg event labels."""

from datetime import datetime, timezone

from ml_models.depeg_events import depeg_probability_at, load_depeg_events
from services.dews import compute_dews


def test_load_depeg_events():
    events = load_depeg_events()
    assert len(events) >= 3
    assert any(e.asset == "USDC" for e in events)


def test_depeg_probability_in_event_window():
    events = load_depeg_events()
    ts = datetime(2023, 3, 11, 12, 0, tzinfo=timezone.utc)
    p1, p6, p24 = depeg_probability_at(ts, "USDC", events)
    assert p24 > 0.5


def test_depeg_probability_outside_window():
    events = load_depeg_events()
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    p1, p6, p24 = depeg_probability_at(ts, "USDC", events)
    assert p24 < 0.1


def test_compute_dews_tiers():
    out = compute_dews(z_score_max=4.0, cross_source_discrepancy_pct=0.5, depeg_probability_24h=0.2)
    assert out["dews_score"] > 0
    assert out["band"] in ("watch", "warning", "critical")
    assert len(out["tiers_fired"]) >= 2


def test_compute_dews_cusum_tier():
    out = compute_dews(cusum_triggered=True)
    assert any(t.get("name") == "cusum" for t in out["tiers_fired"])


def test_compute_dews_llm_tier():
    out = compute_dews(z_score_max=4.0, llm_escalated=True)
    assert any(t.get("tier") == 4 for t in out["tiers_fired"])


def test_compute_dews_all_zero_inputs():
    out = compute_dews()
    assert out["dews_score"] == 0.0
    assert out["band"] == "normal"
    assert out["tiers_fired"] == []
    assert out["tier_count"] == 0


def test_compute_dews_score_capped_at_100():
    out = compute_dews(
        z_score_max=20.0,
        cusum_triggered=True,
        cross_source_discrepancy_pct=5.0,
        depeg_probability_24h=0.99,
        llm_escalated=True,
        whale_alert=True,
        whale_net_outflow_usd=50_000_000,
        top10_holder_share_pct=90.0,
        net_mint_burn_usd_24h=100_000_000,
    )
    assert out["dews_score"] == 100.0
    assert out["band"] == "critical"


def test_compute_dews_whale_flow_boundary():
    below = compute_dews(whale_net_outflow_usd=4_999_999)
    above = compute_dews(whale_net_outflow_usd=5_000_000)
    assert not any(t.get("name") == "whale_flow" for t in below["tiers_fired"])
    assert any(t.get("name") == "whale_flow" for t in above["tiers_fired"])


def test_compute_dews_holder_concentration_boundary():
    below = compute_dews(top10_holder_share_pct=50.0)
    above = compute_dews(top10_holder_share_pct=50.1)
    assert not any(t.get("name") == "holder_concentration" for t in below["tiers_fired"])
    assert any(t.get("name") == "holder_concentration" for t in above["tiers_fired"])


def test_compute_dews_mint_burn_boundary():
    below = compute_dews(net_mint_burn_usd_24h=9_999_999)
    above = compute_dews(net_mint_burn_usd_24h=10_000_000)
    assert not any(t.get("name") == "mint_burn" for t in below["tiers_fired"])
    assert any(t.get("name") == "mint_burn" for t in above["tiers_fired"])


def test_compute_dews_depeg_probability_boundary():
    below = compute_dews(depeg_probability_24h=0.05)
    above = compute_dews(depeg_probability_24h=0.051)
    assert not any(t.get("name") == "model" for t in below["tiers_fired"])
    assert any(t.get("name") == "model" for t in above["tiers_fired"])


def test_compute_dews_zscore_boundary():
    below = compute_dews(z_score_max=3.0)
    above = compute_dews(z_score_max=3.01)
    assert not any(t.get("name") == "statistical" for t in below["tiers_fired"])
    assert any(t.get("name") == "statistical" for t in above["tiers_fired"])


def test_compute_dews_band_transitions():
    assert compute_dews()["band"] == "normal"
    assert compute_dews(z_score_max=4.0)["band"] == "watch"
    assert compute_dews(z_score_max=4.0, cusum_triggered=True, cross_source_discrepancy_pct=0.5)["band"] == "warning"
    assert compute_dews(z_score_max=10.0, cusum_triggered=True, cross_source_discrepancy_pct=2.0, depeg_probability_24h=0.5)["band"] == "critical"


def test_compute_dews_whale_alert_triggers_without_outflow():
    out = compute_dews(whale_alert=True, whale_net_outflow_usd=0)
    assert any(t.get("name") == "whale_flow" for t in out["tiers_fired"])


def test_compute_dews_negative_mint_burn_triggers():
    out = compute_dews(net_mint_burn_usd_24h=-15_000_000)
    assert any(t.get("name") == "mint_burn" for t in out["tiers_fired"])
