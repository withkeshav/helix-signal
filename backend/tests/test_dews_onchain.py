"""DEWS on-chain tier integration tests."""

from services.dews import compute_dews


def test_dews_whale_flow_tier():
    out = compute_dews(
        whale_net_outflow_usd=8_000_000,
        whale_alert=True,
    )
    names = [t["name"] for t in out["tiers_fired"]]
    assert "whale_flow" in names
    assert out["dews_score"] > 0


def test_dews_holder_concentration_tier():
    out = compute_dews(top10_holder_share_pct=65.0)
    names = [t["name"] for t in out["tiers_fired"]]
    assert "holder_concentration" in names
