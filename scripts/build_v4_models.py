#!/usr/bin/env python3
"""Build heuristic ONNX models directly (no skl2onnx limitation).

Requirements: pip install onnx numpy
Run: python scripts/build_v4_models.py
Output: backend/ml_models/helix_*_v4_heuristic.onnx (5 files)

ONNX opset 9: Slice uses attributes (axes, starts, ends).

ReLU variants:
  - relu_sub:  ReLU(feature - constant) * multiplier   [e.g. max(0, spread-5)]
  - relu_rsub: ReLU(constant - feature) * multiplier    [e.g. max(0, 1-coverage)]
"""

from __future__ import annotations

from pathlib import Path

import onnx

MODELS_DIR = Path(__file__).resolve().parent.parent / "backend" / "ml_models"


def _t(name: str, val: float) -> onnx.TensorProto:
    return onnx.helper.make_tensor(name, onnx.TensorProto.FLOAT, [1], [val])


def _make(name: str, n_feat: int, *,
          terms: list[tuple[int, float]] | None = None,
          relu_sub: list[tuple[int, float, float]] | None = None,    # ReLU(feature - C) * M
          relu_rsub: list[tuple[int, float, float]] | None = None,   # ReLU(C - feature) * M
          denom: float = 100.0) -> onnx.ModelProto:
    nodes: list = []
    init: list = []
    inp = "float_input"
    out = "output"
    sums: list[str] = []

    def _linear(idx: int, mult: float, tag: str) -> str:
        c = _t(f"c_{tag}_{idx}", mult)
        init.append(c)
        s = f"s_{tag}_{idx}"
        nodes.append(onnx.helper.make_node("Slice", [inp], [s], axes=[1], starts=[idx], ends=[idx + 1]))
        m = f"m_{tag}_{idx}"
        nodes.append(onnx.helper.make_node("Mul", [s, c.name], [m]))
        return m

    def _relu_sub(idx: int, mult: float, const: float, tag: str) -> str:
        """ReLU(feature - const) * mult"""
        cm = _t(f"rm_{tag}_{idx}", mult)
        cc = _t(f"rc_{tag}_{idx}", const)
        init.extend([cm, cc])
        s = f"rs_{tag}_{idx}"
        nodes.append(onnx.helper.make_node("Slice", [inp], [s], axes=[1], starts=[idx], ends=[idx + 1]))
        sub = f"rsub_{tag}_{idx}"
        nodes.append(onnx.helper.make_node("Sub", [s, cc.name], [sub]))
        rel = f"rrel_{tag}_{idx}"
        nodes.append(onnx.helper.make_node("Relu", [sub], [rel]))
        mul = f"rmul_{tag}_{idx}"
        nodes.append(onnx.helper.make_node("Mul", [rel, cm.name], [mul]))
        return mul

    def _relu_rsub(idx: int, mult: float, const: float, tag: str) -> str:
        """ReLU(const - feature) * mult"""
        cm = _t(f"rm_{tag}_{idx}", mult)
        cc = _t(f"rc_{tag}_{idx}", const)
        init.extend([cm, cc])
        s = f"rs_{tag}_{idx}"
        nodes.append(onnx.helper.make_node("Slice", [inp], [s], axes=[1], starts=[idx], ends=[idx + 1]))
        sub = f"rsub_{tag}_{idx}"
        nodes.append(onnx.helper.make_node("Sub", [cc.name, s], [sub]))
        rel = f"rrel_{tag}_{idx}"
        nodes.append(onnx.helper.make_node("Relu", [sub], [rel]))
        mul = f"rmul_{tag}_{idx}"
        nodes.append(onnx.helper.make_node("Mul", [rel, cm.name], [mul]))
        return mul

    if terms:
        for idx, mult in terms:
            sums.append(_linear(idx, mult, "lin"))

    if relu_sub:
        for idx, mult, const in relu_sub:
            sums.append(_relu_sub(idx, mult, const, "sub"))

    if relu_rsub:
        for idx, mult, const in relu_rsub:
            sums.append(_relu_rsub(idx, mult, const, "rsub"))

    cur = sums[0]
    for i, o in enumerate(sums[1:], 1):
        nxt = f"a_{i}"
        nodes.append(onnx.helper.make_node("Add", [cur, o], [nxt]))
        cur = nxt

    d = _t("den", denom)
    init.append(d)
    dv = "dv"
    nodes.append(onnx.helper.make_node("Div", [cur, d.name], [dv]))

    nodes.append(onnx.helper.make_node("Clip", [dv], [out], min=0.0, max=1.0))

    g = onnx.helper.make_graph(
        nodes, name,
        [onnx.helper.make_tensor_value_info(inp, onnx.TensorProto.FLOAT, [None, n_feat])],
        [onnx.helper.make_tensor_value_info(out, onnx.TensorProto.FLOAT, [None, 1])],
        init,
    )
    m = onnx.helper.make_model(g, opset_imports=[onnx.helper.make_opsetid("", 9)], ir_version=8)
    return onnx.shape_inference.infer_shapes(m)


def _build_funding_regime():
    """Regime classifier: output 0 (NEGATIVE), 1 (NEUTRAL), or 2 (POSITIVE).

    Rules:
      NEGATIVE (0): funding_rate_current < -0.0001 AND neg_hours >= 4
      POSITIVE (2): funding_rate_7d_avg > 0.0003
      NEUTRAL  (1): everything else
    """
    nodes: list = []
    init: list = []
    inp = "float_input"
    out = "output"

    neg_thresh = _t("neg_th", -0.0001)
    neg_hours_th = _t("neg_hrs", 4.0)
    pos_th = _t("pos_th", 0.0003)
    c1 = _t("one", 1.0)
    init.extend([neg_thresh, neg_hours_th, pos_th, c1])

    for idx, name in [(0, "cur"), (1, "avg"), (2, "nh")]:
        nodes.append(onnx.helper.make_node("Slice", [inp], [name], axes=[1], starts=[idx], ends=[idx + 1]))

    neg_less = "neg_less"
    nodes.append(onnx.helper.make_node("Less", ["cur", neg_thresh.name], [neg_less]))
    nh_less = "nh_less"
    nodes.append(onnx.helper.make_node("Less", ["nh", neg_hours_th.name], [nh_less]))
    nh_not = "nh_not"
    nodes.append(onnx.helper.make_node("Not", [nh_less], [nh_not]))
    neg_and = "neg_and"
    nodes.append(onnx.helper.make_node("And", [neg_less, nh_not], [neg_and]))

    pos_gt = "pos_gt"
    nodes.append(onnx.helper.make_node("Greater", ["avg", pos_th.name], [pos_gt]))

    neg_f = "neg_f"
    pos_f = "pos_f"
    nodes.append(onnx.helper.make_node("Cast", [neg_and], [neg_f], to=1))
    nodes.append(onnx.helper.make_node("Cast", [pos_gt], [pos_f], to=1))

    add1 = "add1"
    nodes.append(onnx.helper.make_node("Add", [c1.name, pos_f], [add1]))
    sub1 = "sub1"
    nodes.append(onnx.helper.make_node("Sub", [add1, neg_f], [sub1]))
    nodes.append(onnx.helper.make_node("Cast", [sub1], [out], to=7))

    g = onnx.helper.make_graph(
        nodes, "funding_regime",
        [onnx.helper.make_tensor_value_info(inp, onnx.TensorProto.FLOAT, [None, 4])],
        [onnx.helper.make_tensor_value_info(out, onnx.TensorProto.INT64, [None, 1])],
        init,
    )
    m = onnx.helper.make_model(g, opset_imports=[onnx.helper.make_opsetid("", 9)], ir_version=8)
    return onnx.shape_inference.infer_shapes(m)


def build_all():
    # Fiat: price_dev*0.4 + ReLU(1-coverage)*30 + attest_lag*0.5 + reg_flag*20
    fiat = _make("fiat_v4", 7,
        terms=[(0, 0.4), (2, 0.5), (6, 20.0)],
        relu_rsub=[(1, 30.0, 1.0)])
    onnx.save(fiat, str(MODELS_DIR / "helix_fiat_depeg_v4_heuristic.onnx"))

    # Crypto: price_dev*0.3 + ReLU(150-coll_ratio)*0.5 + liq_queue*20 + debt_ceil*0.2
    crypto = _make("crypto_v4", 6,
        terms=[(0, 0.3), (3, 20.0), (4, 0.2)],
        relu_rsub=[(1, 0.5, 150.0)])
    onnx.save(crypto, str(MODELS_DIR / "helix_crypto_collateral_depeg_v4_heuristic.onnx"))

    # Delta: price_dev*0.3 + ReLU(-funding)*500 + ReLU(0.02-insurance)*1000 + ReLU(-perp_oi)*2
    # max(0, -funding) = ReLU(0 - funding), max(0, 0.02-insurance) = ReLU(0.02 - ins), max(0, -perp_oi) = ReLU(0 - perp_oi)
    delta = _make("delta_v4", 6,
        terms=[(0, 0.3)],
        relu_rsub=[(1, 500.0, 0.0), (3, 1000.0, 0.02), (5, 2.0, 0.0)])
    onnx.save(delta, str(MODELS_DIR / "helix_delta_neutral_depeg_v4_heuristic.onnx"))

    # Funding regime
    fr = _build_funding_regime()
    onnx.save(fr, str(MODELS_DIR / "helix_funding_regime_v4_heuristic.onnx"))

    # Yield sustainability:
    # risk = max(0, spread-5)*0.05 + max(0, -apy_delta)*0.1 + risk_score*0.3
    #      + max(0, -tvl_change)*0.02 + max(0, util-0.85)*2
    # relu_sub for: spread-5, util-0.85
    # relu_rsub for: -apy_delta (= 0-apy_delta), -tvl_change (= 0-tvl_change)
    ys = _make("yield_sustainability_v4", 6,
        terms=[(2, 0.3)],
        relu_sub=[(0, 0.05, 5.0), (4, 2.0, 0.85)],
        relu_rsub=[(1, 0.1, 0.0), (3, 0.02, 0.0)],
        denom=1.0,
    )
    onnx.save(ys, str(MODELS_DIR / "helix_yield_sustainability_v4_heuristic.onnx"))

    print(f"5 ONNX models built. Checking validity...")
    for f in ["helix_fiat_depeg_v4_heuristic.onnx",
              "helix_crypto_collateral_depeg_v4_heuristic.onnx",
              "helix_delta_neutral_depeg_v4_heuristic.onnx",
              "helix_funding_regime_v4_heuristic.onnx",
              "helix_yield_sustainability_v4_heuristic.onnx"]:
        m = onnx.load(str(MODELS_DIR / f))
        onnx.checker.check_model(m)
        print(f"  {f}: OK ({len(m.SerializeToString()) / 1024:.1f} KB)")


if __name__ == "__main__":
    build_all()
