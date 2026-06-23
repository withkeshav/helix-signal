from signal_engine import scoring


def test_peg_deviation_healthy():
    dev, pct = scoring.peg_deviation(1.0)
    assert dev == 0.0
    assert pct == 0.0


def test_depeg_index_increases_with_deviation():
    low = scoring.depeg_index_score(1.0005)
    high = scoring.depeg_index_score(0.99)
    assert high > low


def test_concentration_hhi_single_chain():
    score, detail = scoring.concentration_component([1.0])
    assert score >= 0
    assert detail["top_chain_share_pct"] == 100.0


def test_velocity_contracting_supply_contributes():
    from signal_engine.components.composite_scoring import compute_risk_score
    pos = compute_risk_score(price=1.0, chain_shares=[0.5, 0.5], supply_velocity_1h=2.0, supply_velocity_4h=0, age_seconds=0)
    neg = compute_risk_score(price=1.0, chain_shares=[0.5, 0.5], supply_velocity_1h=-2.0, supply_velocity_4h=0, age_seconds=0)
    assert neg["components"]["velocity"]["score"] == pos["components"]["velocity"]["score"]
    assert neg["components"]["velocity"]["score"] > 0


def test_liquidity_depth_component():
    from signal_engine.components.composite_scoring import compute_risk_score
    low = compute_risk_score(price=1.0, chain_shares=[0.5, 0.5], slippage_100k_bps=3, age_seconds=0)
    high = compute_risk_score(price=1.0, chain_shares=[0.5, 0.5], slippage_100k_bps=120, age_seconds=0)
    assert "liquidity_depth" in low["components"]
    assert high["components"]["liquidity_depth"]["score"] > low["components"]["liquidity_depth"]["score"]


def test_composite_bands():
    assert scoring.composite_band(10) == "Healthy"
    assert scoring.composite_band(50) == "Watch"
    assert scoring.composite_band(80) == "Alert"
