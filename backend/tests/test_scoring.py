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


def test_composite_bands():
    assert scoring.composite_band(10) == "Healthy"
    assert scoring.composite_band(50) == "Watch"
    assert scoring.composite_band(80) == "Alert"
