"""Tests for alert rule evaluation engine."""

from datetime import datetime, timezone

from services.alerts import (
    _eval_depeg_bps,
    _eval_supply_contraction,
    _eval_freshness,
    _eval_source_error,
    _eval_concentration,
    _eval_slippage,
    _match_condition,
    _extract_threshold,
    load_alert_rules,
)


def test_extract_threshold():
    assert _extract_threshold("depeg_bps > 50", "depeg_bps > ") == 50.0
    assert _extract_threshold("supply_change_7d < -3", "supply_change_7d < ") == -3.0
    assert _extract_threshold("freshness_age_minutes > 10", "freshness_age_minutes > ") == 10.0


def test_match_condition():
    fn = _match_condition("depeg_bps > 50")
    assert fn is not None
    assert fn.__name__ == "_eval_depeg_bps"


def test_match_condition_longest_prefix():
    fn = _match_condition("source_status = error for > 5 min")
    assert fn is not None
    assert "persistent" in fn.__name__ or "for" in fn.__name__ or fn.__name__ == "_eval_source_error_persistent"

    fn2 = _match_condition("source transitions error -> ok")
    assert fn2 is not None
    assert "recovered" in fn2.__name__


def test_match_unknown_condition():
    assert _match_condition("nonexistent > 99") is None


def test_eval_depeg_bps_triggers():
    bundle = {"price": 0.993, "_meta": {}}
    rule = {"condition": "depeg_bps > 50"}
    assert _eval_depeg_bps(bundle, rule) is True
    assert bundle["_meta"]["depeg_bps"] > 50


def test_eval_depeg_bps_no_trigger():
    assert _eval_depeg_bps({"price": 1.001, "_meta": {}}, {"condition": "depeg_bps > 50"}) is False


def test_eval_supply_contraction_triggers():
    assert _eval_supply_contraction(
        {"supply_change_7d_pct": -5.0, "_meta": {}},
        {"condition": "supply_change_7d < -3"},
    ) is True


def test_eval_supply_contraction_no_trigger():
    assert _eval_supply_contraction(
        {"supply_change_7d_pct": -1.0, "_meta": {}},
        {"condition": "supply_change_7d < -3"},
    ) is False


def test_eval_freshness_triggers():
    bundle = {"freshness_age_seconds": 3600, "_meta": {}}
    assert _eval_freshness(bundle, {"condition": "freshness_age_minutes > 10"}) is True
    assert bundle["_meta"]["age_minutes"] == 60.0


def test_eval_freshness_no_trigger():
    assert _eval_freshness(
        {"freshness_age_seconds": 300, "_meta": {}},
        {"condition": "freshness_age_minutes > 10"},
    ) is False


def test_eval_concentration_triggers():
    assert _eval_concentration(
        {"top3_pool_share_pct": 85.0, "_meta": {}},
        {"condition": "top3_pool_share > 80"},
    ) is True


def test_eval_concentration_no_trigger():
    assert _eval_concentration(
        {"top3_pool_share_pct": 50.0, "_meta": {}},
        {"condition": "top3_pool_share > 80"},
    ) is False


def test_load_alert_rules_structure():
    rules = load_alert_rules()
    assert len(rules) >= 1
    for r in rules:
        assert "type" in r
        assert "condition" in r
        assert "severity" in r
