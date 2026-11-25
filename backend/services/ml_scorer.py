"""Score the latest closed bar of an instrument with the trained model."""
import json
import threading

import joblib
import numpy as np

from config import ASSET_CLASS, COST, LABELS, MODEL_DIR, RISK_REWARD
from services.indicators import FEATURES
from services.risk import levels
from services.training import BUY, SELL, decide

_bundles: dict = {}
_lock = threading.Lock()


def bundle(tf):
    """Load the model once; reload automatically after a retrain. None if not trained yet."""
    f = MODEL_DIR / f"model_{tf}.joblib"
    if not f.exists():
        return None
    stamp = f.stat().st_mtime
    with _lock:
        if tf not in _bundles or _bundles[tf][0] != stamp:
            b = joblib.load(f)                 # only ever our own file, written by training.py
            if b["features"] != FEATURES:
                raise RuntimeError("model is out of date: run `python train.py`")
            b["forest"].n_jobs = 1
            _bundles[tf] = (stamp, b)
        return _bundles[tf][1]


def report(tf):
    f = MODEL_DIR / f"report_{tf}.json"
    return json.loads(f.read_text()) if f.exists() else None


def explain(forest, x, cls):
    """Per-feature contribution to P(cls): change in class share along each tree path (Saabas)."""
    out = np.zeros(len(FEATURES))
    for est in forest.estimators_:
        t = est.tree_
        node = 0
        while t.children_left[node] != -1:
            f = t.feature[node]
            nxt = t.children_left[node] if x[f] <= t.threshold[node] else t.children_right[node]
            a, b = t.value[node][0], t.value[nxt][0]
            out[f] += b[cls] / b.sum() - a[cls] / a.sum()
            node = nxt
    return out / len(forest.estimators_)


def guess_class(symbol):
    if symbol in ASSET_CLASS:
        return ASSET_CLASS[symbol]
    if symbol.endswith("=X"):
        return "forex"
    if symbol.endswith("=F"):
        return "commodity"
    if symbol.startswith("^"):
        return "index"
    if symbol.endswith(("-USD", "-EUR", "-INR", "-GBP")):
        return "crypto"
    return "stock"


def score(d, symbol, tf, currency):
    """`d` = output of indicators.compute(). User-independent; sizing is added per request."""
    b = bundle(tf)
    if b is None or d is None or d.empty:
        return None
    row = d.iloc[-1]
    asset = guess_class(symbol)
    x = row[FEATURES].to_numpy(float)
    proba = b["model"].predict_proba(x.reshape(1, -1))
    entry, atr = float(row["Close"]), float(row["atr"])
    stop_dist = abs(entry - levels(entry, atr, 1)[0])
    cost_r = COST[asset] * entry / stop_dist
    side, p, ev = (v[0] for v in decide(proba, cost_r, b["nonwin_r"]))
    lean = 1 if proba[0, BUY] >= proba[0, SELL] else -1
    contrib = explain(b["forest"], x.astype(np.float32), BUY if lean > 0 else SELL)
    stop, target = levels(entry, atr, lean)
    nw = b["nonwin_r"]
    breakeven = (cost_r - nw) / (RISK_REWARD - nw)
    return {
        "symbol": symbol, "label": LABELS.get(symbol, symbol), "asset": asset, "timeframe": tf,
        "currency": currency, "bar_time": d.index[-1].isoformat(),
        "direction": {1: "BUY", -1: "SELL", 0: "NEUTRAL"}[int(side)],
        "lean": "BUY" if lean > 0 else "SELL", "side": int(lean),
        "p_win": float(p), "p_breakeven": float(breakeven), "expected_r": float(ev),
        "probs": {"SELL": float(proba[0, 0]), "NEUTRAL": float(proba[0, 1]), "BUY": float(proba[0, 2])},
        # TradeScore = P_win * RR / sigma; sigma = volatility relative to the instrument's own norm
        "trade_score": float(p * RISK_REWARD / row["atr_rel"]),
        "entry": entry, "stop": float(stop), "target": float(target),
        "risk_reward": RISK_REWARD, "atr": atr, "cost_r": float(cost_r),
        "indicators": {f: float(row[f]) for f in FEATURES},
        "drivers": sorted(({"feature": f, "value": float(v), "impact": float(c)}
                           for f, v, c in zip(FEATURES, x, contrib)),
                          key=lambda z: -abs(z["impact"])),
        "spark": [float(v) for v in d["Close"].iloc[-60:]],
    }
