"""Walk-forward evaluation, baselines and final model fitting."""
import heapq
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix,
                             log_loss, precision_score, recall_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from config import (ASSET_CLASS, ATR_STOP, BACKTEST_RISK, COST, HORIZON, MODEL_DIR, RANDOM_SEED,
                    RISK_REWARD, TIMEFRAMES, TOP_N, UNIVERSE, WILLIAMS_R_OVERBOUGHT,
                    WILLIAMS_R_OVERSOLD)
from services.data_fetcher import fetch
from services.indicators import FEATURES, compute
from services.risk import outcomes

SELL, NEUTRAL, BUY = 0, 1, 2
FOLDS = 5


def models():
    rf = dict(n_estimators=300, max_depth=8, min_samples_leaf=50, n_jobs=-1, random_state=RANDOM_SEED)
    return {
        "majority": DummyClassifier(strategy="prior"),
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "tree": DecisionTreeClassifier(max_depth=6, min_samples_leaf=200, random_state=RANDOM_SEED),
        "gradient_boosting": HistGradientBoostingClassifier(
            max_depth=4, learning_rate=0.05, max_iter=150, random_state=RANDOM_SEED),
        "random_forest": RandomForestClassifier(**rf),
    }


def label(d: pd.DataFrame) -> pd.Series:
    """Triple barrier: BUY if a long hits its target first, SELL if a short does.

    Long- and short-wins are mutually exclusive because the stop is nearer than the target.
    """
    return pd.Series(np.select([d["win_long"], d["win_short"]], [BUY, SELL], NEUTRAL), index=d.index)


def dataset(tf: str) -> pd.DataFrame:
    def one(sym):
        got = fetch(sym, tf, TIMEFRAMES[tf]["train"])
        if got is None:
            return None
        d = compute(got[0])
        if len(d) < 500:
            return None
        d = d.join(outcomes(d))
        idx = d.index.to_series()
        d["t"] = d.index
        d["t_end"] = idx.shift(-HORIZON).to_numpy()
        d["symbol"] = sym
        d["cost_r"] = COST[ASSET_CLASS[sym]] * d["Close"] / (ATR_STOP * d["atr"])
        d["fwd"] = d["Close"].pct_change().shift(-1)
        for s in ("long", "short"):                       # exit timestamp per side
            pos = np.minimum(np.arange(len(d)) + d[f"bars_{s}"].to_numpy(), len(d) - 1)
            d[f"exit_{s}"] = d.index[pos]
        d = d.dropna(subset=["r_long", "r_short", "t_end"])
        d["y"] = label(d)
        return d

    with ThreadPoolExecutor(6) as ex:
        parts = [p for p in ex.map(one, ASSET_CLASS) if p is not None]
    if not parts:
        raise RuntimeError("no market data available")
    return pd.concat(parts, ignore_index=True).sort_values("t", kind="stable").reset_index(drop=True)


def purge(d, before):
    """Rows whose label is fully known before `before` (no look-ahead)."""
    return d[d["t_end"] < before]


def thin(train):
    """Labels of neighbouring bars overlap almost fully; keep every n-th bar of large sets."""
    n = max(1, len(train) // 60000)
    return train if n == 1 else train[train.groupby("symbol").cumcount() % n == 0]


def fit_calibrated(est, train):
    """Fit on the older 80%, Platt-calibrate on the newest 20%, purged in between."""
    train = thin(train)
    cut = train["t"].quantile(0.8)
    fit, cal = purge(train, cut), train[train["t"] >= cut]
    est.fit(fit[FEATURES].to_numpy(), fit["y"])
    if isinstance(est, DummyClassifier):
        return est
    c = CalibratedClassifierCV(FrozenEstimator(est), method="sigmoid")
    return c.fit(cal[FEATURES].to_numpy(), cal["y"])


def nonwin_r(train):
    """Average R of trades that miss the target (stops and time-outs), from training data."""
    w = train["win_long"].to_numpy(bool)
    s = train["win_short"].to_numpy(bool)
    return float(np.concatenate([train["r_long"].to_numpy()[~w], train["r_short"].to_numpy()[~s]]).mean())


def decide(proba, cost_r, nw):
    """-> (side -1/0/+1, p_win, expected R after costs). Trades only on positive expectancy."""
    p_sell, p_buy = proba[:, SELL], proba[:, BUY]
    side = np.where(p_buy >= p_sell, 1, -1)
    p = np.maximum(p_buy, p_sell)
    ev = p * RISK_REWARD + (1 - p) * nw - cost_r
    return np.where(ev > 0, side, 0), p, ev


def rule_side(d):
    up = d["ema_spread"] > 0
    return np.select([up & (d["williams_r"] < WILLIAMS_R_OVERSOLD),
                      ~up & (d["williams_r"] > WILLIAMS_R_OVERBOUGHT)], [1, -1], 0)


def portfolio(d, side, score):
    """Sequential simulation: one trade per symbol, at most TOP_N open at once."""
    m = side != 0
    c = pd.DataFrame({
        "t": d["t"][m], "symbol": d["symbol"][m], "score": score[m],
        "exit": np.where(side[m] > 0, d["exit_long"][m].astype("int64"), d["exit_short"][m].astype("int64")),
        "r": np.where(side[m] > 0, d["r_long"][m], d["r_short"][m]) - d["cost_r"][m],
        "win": np.where(side[m] > 0, d["win_long"][m], d["win_short"][m]),
    })
    c["ti"] = c["t"].astype("int64")
    c = c.sort_values(["ti", "score"], ascending=[True, False])
    open_, held, keep = [], set(), []
    for i, (ti, sym, ex) in enumerate(zip(c["ti"], c["symbol"], c["exit"])):
        while open_ and open_[0][0] <= ti:
            held.discard(heapq.heappop(open_)[1])
        if sym in held or len(open_) >= TOP_N:
            continue
        heapq.heappush(open_, (ex, sym))
        held.add(sym)
        keep.append(i)
    c = c.iloc[keep].copy()
    c["exit"] = pd.to_datetime(c["exit"], unit=d["exit_long"].dt.unit, utc=True)
    return c


def _curve_stats(daily: pd.Series):
    if len(daily) < 2 or daily.std() == 0:
        return {"sharpe": None, "max_drawdown": None, "total_return": None}
    eq = (1 + daily.clip(lower=-0.99)).cumprod()
    dd = eq / eq.cummax().clip(lower=1) - 1
    return {"sharpe": round(float(np.sqrt(252) * daily.mean() / daily.std()), 2),
            "max_drawdown": round(float(dd.min()), 4), "total_return": round(float(eq.iloc[-1] - 1), 4)}


def _business(start, end):
    return pd.bdate_range(start.normalize(), end.normalize(), tz="UTC")


def trade_stats(tr, start, end):
    if tr.empty:
        return {"trades": 0, "win_rate": None, "avg_r": None, "profit_factor": None, "ci": None,
                "sharpe": None, "max_drawdown": None, "total_return": None}
    days = _business(start, end)
    by_day = (tr["r"] * BACKTEST_RISK).groupby(tr["exit"].dt.normalize()).sum()
    at = np.clip(days.searchsorted(by_day.index), 0, len(days) - 1)   # weekends -> next business day
    daily = pd.Series(np.bincount(at, weights=by_day.to_numpy(), minlength=len(days)), index=days)
    # Cluster bootstrap by exit week: simultaneous trades are not independent.
    wk = tr["exit"].dt.strftime("%G-%V")
    g = tr["r"].groupby(wk).agg(["sum", "count"]).to_numpy()
    rng = np.random.default_rng(RANDOM_SEED)
    s = g[rng.integers(0, len(g), (2000, len(g)))].sum(axis=1)
    lo, hi = np.percentile(s[:, 0] / s[:, 1], [2.5, 97.5])
    gain, loss = tr["r"][tr["r"] > 0].sum(), -tr["r"][tr["r"] < 0].sum()
    return {"trades": int(len(tr)), "win_rate": round(float((tr["r"] > 0).mean()), 4),
            "avg_r": round(float(tr["r"].mean()), 4), "ci": [round(float(lo), 4), round(float(hi), 4)],
            "profit_factor": round(float(gain / loss), 3) if loss else None,
            **_curve_stats(daily)}


def class_stats(y, side):
    pred = np.asarray(side) + 1
    kw = dict(average="macro", labels=[0, 1, 2], zero_division=0)
    return {"accuracy": round(accuracy_score(y, pred), 4),
            "balanced_accuracy": round(balanced_accuracy_score(y, pred), 4),
            "precision": round(precision_score(y, pred, **kw), 4),
            "recall": round(recall_score(y, pred, **kw), 4),
            "confusion": confusion_matrix(y, pred, labels=[0, 1, 2]).tolist()}


def evaluate(d, log=print):
    """Expanding-window, purged walk-forward. All numbers are out-of-sample."""
    ts = d["t"]
    edges = [ts.quantile(q) for q in np.linspace(0.5, 1.0, FOLDS + 1)]
    edges[-1] += pd.Timedelta(days=1)
    names = list(models())
    parts, probs = [], {n: [] for n in names}
    nws, fold_imp = [], None
    for k in range(FOLDS):
        train, test = purge(d, edges[k]), d[(ts >= edges[k]) & (ts < edges[k + 1])]
        nw = nonwin_r(train)
        nws.append(np.full(len(test), nw))
        parts.append(test)
        for n, est in models().items():
            t0 = time.time()
            m = fit_calibrated(est, train)
            probs[n].append(m.predict_proba(test[FEATURES].to_numpy()))
            log(f"  fold {k + 1}/{FOLDS} {n}: {len(train)} train / {len(test)} test ({time.time() - t0:.0f}s)")
            if n == "random_forest" and k == FOLDS - 1:
                sm = test.sample(min(8000, len(test)), random_state=RANDOM_SEED)
                fold_imp = permutation_importance(m, sm[FEATURES].to_numpy(), sm["y"], n_repeats=5,
                                                  scoring="neg_log_loss", random_state=RANDOM_SEED)
    oos, nw = pd.concat(parts).reset_index(drop=True), np.concatenate(nws)
    start, end = oos["t"].min(), oos["t"].max()
    cost, y = oos["cost_r"].to_numpy(), oos["y"].to_numpy()
    res = {}
    for n in names:
        P = np.vstack(probs[n])
        side, p, ev = decide(P, cost, nw)
        tr = portfolio(oos, side, p * RISK_REWARD / oos["atr_rel"].to_numpy())
        res[n] = {**class_stats(y, side), "log_loss": round(log_loss(y, P, labels=[0, 1, 2]), 4),
                  **trade_stats(tr, start, end)}
        if n == "random_forest":
            cal = []
            for b, g in pd.DataFrame({"b": pd.qcut(p, 10, duplicates="drop", labels=False), "p": p,
                                      "w": np.where(P[:, BUY] >= P[:, SELL], y == BUY, y == SELL)}).groupby("b"):
                cal.append([round(g["p"].mean(), 4), round(g["w"].mean(), 4)])
            res[n]["calibration"] = cal
            eq = (1 + tr.groupby(tr["exit"].dt.normalize())["r"].sum() * BACKTEST_RISK).cumprod() \
                if len(tr) else pd.Series(dtype=float)
            step = max(1, len(eq) // 150)
            res[n]["equity"] = [[t.strftime("%Y-%m-%d"), round(float(v), 4)] for t, v in eq.iloc[::step].items()]
            res[n]["by_class"] = {
                a: trade_stats(tr[tr["symbol"].map(ASSET_CLASS) == a], start, end) for a in UNIVERSE}
    rs = rule_side(oos)
    tr = portfolio(oos, rs, 1 / oos["atr_rel"].to_numpy())
    res["rule_only"] = {**class_stats(y, rs), "log_loss": None, **trade_stats(tr, start, end)}
    day = oos["t"].dt.normalize()
    day += pd.to_timedelta((7 - day.dt.weekday).where(day.dt.weekday >= 5, 0), unit="D")  # weekend -> Monday
    bh = oos.assign(day=day).groupby(["day", "symbol"])["fwd"].apply(lambda x: (1 + x).prod() - 1)
    res["buy_and_hold"] = _curve_stats(bh.groupby("day").mean())
    imp = {f: round(float(v), 5) for f, v in zip(FEATURES, fold_imp.importances_mean)}
    share = np.bincount(y, minlength=3) / len(y)
    return {"results": res, "importance": imp,
            "class_share": dict(zip(["SELL", "NEUTRAL", "BUY"], share.round(4).tolist())),
            "oos": [start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")], "n_oos": int(len(oos))}


def edge_proven(res) -> bool:
    """Profit alone proves nothing in a rising market with hand-picked survivors: the model
    must be significantly profitable AND beat the no-skill baseline on profit and log-loss."""
    rf, base = res["random_forest"], res["majority"]
    return bool(rf["ci"] and rf["ci"][0] > 0 and rf["avg_r"] > (base["avg_r"] or 0)
                and rf["log_loss"] < base["log_loss"])


def train(tf: str, log=print) -> dict:
    log(f"[train] {tf}: loading data")
    d = dataset(tf)
    log(f"[train] {tf}: {len(d)} rows, {d['symbol'].nunique()} instruments")
    rep = evaluate(d, log)
    rf = models()["random_forest"]
    cal = fit_calibrated(rf, d)
    rep.update({
        "timeframe": tf, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(d)), "instruments": sorted(d["symbol"].unique().tolist()),
        "data": [d["t"].min().strftime("%Y-%m-%d"), d["t"].max().strftime("%Y-%m-%d")],
        "params": {"horizon": HORIZON, "atr_stop": ATR_STOP, "risk_reward": RISK_REWARD, "folds": FOLDS,
                   "top_n": TOP_N, "cost": COST, "rf": {k: rf.get_params()[k] for k in
                                           ("n_estimators", "max_depth", "min_samples_leaf")}},
        "sklearn": sklearn.__version__,
        "edge_proven": edge_proven(rep["results"]),
    })
    MODEL_DIR.mkdir(exist_ok=True)
    tmp = MODEL_DIR / f"model_{tf}.tmp"
    joblib.dump({"model": cal, "forest": rf, "nonwin_r": nonwin_r(d), "features": FEATURES,
                 "sklearn": sklearn.__version__}, tmp, compress=3)
    (MODEL_DIR / f"report_{tf}.json").write_text(json.dumps(rep, indent=1, default=float))
    tmp.replace(MODEL_DIR / f"model_{tf}.joblib")        # atomic: readers never see half a file
    log(f"[train] {tf}: saved")
    return rep
