"""python -m unittest  (offline: no network, no trained model required)"""
import os
import tempfile
import unittest
from unittest import mock

os.environ.update(ITDSS_BACKGROUND="0", ITDSS_DATA_DIR=tempfile.mkdtemp(), ITDSS_ADMIN_TOKEN="secret")

import numpy as np
import pandas as pd

from config import HORIZON, RISK_REWARD
from services import journal, training
from services.data_fetcher import clean, fx_rate
from services.indicators import FEATURES, compute
from services.risk import levels, outcomes, position, resolve, size_multiplier


def bars(n=1500, seed=0, scale=1.0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.001, n))
    h = np.maximum(o, c) * (1 + abs(rng.normal(0, 0.002, n)))
    l = np.minimum(o, c) * (1 - abs(rng.normal(0, 0.002, n)))
    ix = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 0.0}, ix) * scale


class Features(unittest.TestCase):
    def test_scale_free(self):
        a, b = compute(bars()), compute(bars(scale=150.0))
        np.testing.assert_allclose(a[FEATURES], b[FEATURES], rtol=1e-6, atol=1e-6)

    def test_no_lookahead(self):
        full, cut = compute(bars()), compute(bars().iloc[:1000])
        np.testing.assert_allclose(full.loc[cut.index, FEATURES], cut[FEATURES], rtol=1e-9)


class Outcomes(unittest.TestCase):
    def test_vectorised_matches_scalar(self):
        d = compute(bars())
        out = outcomes(d)
        for i in range(0, len(d) - HORIZON - 1, 7):
            for side, nm in ((1, "long"), (-1, "short")):
                e, a = d["Close"].iloc[i], d["atr"].iloc[i]
                st, r = resolve(d.iloc[i + 1:], e, *levels(e, a, side), side)
                self.assertAlmostEqual(r, out[f"r_{nm}"].iloc[i], places=9)
                self.assertEqual(st == "win", bool(out[f"win_{nm}"].iloc[i]))

    def test_unfinished_rows_are_not_labelled(self):
        out = outcomes(compute(bars()))
        self.assertTrue(out["r_long"].iloc[-HORIZON:].isna().all())
        self.assertTrue(out["r_long"].iloc[:-HORIZON].notna().all())

    def test_long_and_short_wins_exclusive(self):
        out = outcomes(compute(bars()))
        self.assertFalse((out["win_long"] & out["win_short"]).any())

    def test_gap_and_tie_rules(self):
        def one(o, h, l, c):
            return pd.DataFrame([[o, h, l, c]], columns=["Open", "High", "Low", "Close"])
        self.assertEqual(resolve(one(100, 110, 90, 100), 100, 97, 106, 1)[0], "loss")        # tie -> stop
        self.assertAlmostEqual(resolve(one(94, 95, 93, 94), 100, 97, 106, 1)[1], -2.0)       # gap -> fill at open
        self.assertEqual(resolve(one(107, 108, 90, 95), 100, 97, 106, 1), ("win", RISK_REWARD))
        self.assertIsNone(resolve(one(100, 101, 99, 100), 100, 97, 106, 1))


class Sizing(unittest.TestCase):
    def test_usdjpy_in_usd(self):                      # v1 returned 3,898 units: risk was read as yen
        p = position(158.982, 159.2385, "forex", 100_000, 1, 1 / 158.982)
        self.assertAlmostEqual(p["risk_amount"], 1000, delta=1)
        self.assertGreater(p["units"], 600_000)

    def test_leverage_cap(self):
        p = position(60_000, 59_990, "crypto", 10_000, 1, 1.0)
        self.assertTrue(p["capped"])
        self.assertLessEqual(p["leverage"], 2)

    def test_multiplier_never_raises_risk(self):
        for p in np.linspace(0, 1, 50):
            self.assertTrue(0.5 <= size_multiplier(p, 0.35) <= 1)

    def test_pence(self):
        self.assertEqual(fx_rate("GBp", "GBP"), 0.01)


class Data(unittest.TestCase):
    def test_drops_open_bar_and_duplicates(self):
        d = bars(50)
        now = d.index[-1] + pd.Timedelta(minutes=30)
        got = clean(pd.concat([d, d.iloc[[10]]]), 60, now)
        self.assertEqual(got.index[-1], d.index[-2])
        self.assertTrue(got.index.is_unique)


class Training(unittest.TestCase):
    def test_decide_is_direction_aware(self):
        P = np.array([[.6, .3, .1], [.1, .3, .6], [.2, .6, .2]])
        side, p, _ = training.decide(P, np.zeros(3), -0.9)
        self.assertEqual(side.tolist(), [-1, 1, 0])
        self.assertEqual(p[0], p[1])                  # a strong SELL ranks like a strong BUY

    def test_purge(self):
        t = pd.date_range("2025-01-01", periods=100, freq="h", tz="UTC").to_series().reset_index(drop=True)
        d = pd.DataFrame({"t": t, "t_end": t.shift(-HORIZON)}).dropna()
        self.assertLess(training.purge(d, t[60])["t"].max(), t[60 - HORIZON])

    def test_drift_is_not_an_edge(self):
        base = {"avg_r": .2, "log_loss": 1.07}
        rf = {"avg_r": .1, "ci": [.05, .15], "log_loss": 1.06}
        self.assertFalse(training.edge_proven({"random_forest": rf, "majority": base}))
        self.assertTrue(training.edge_proven({"random_forest": {**rf, "avg_r": .3}, "majority": base}))


class Journal(unittest.TestCase):
    def test_record_dedupe_settle(self):
        d = bars(300)
        e = float(d["Close"].iloc[100])
        t = dict(symbol="T", timeframe="1h", bar_time=d.index[100].isoformat(), side=1, direction="BUY",
                 p_win=.5, entry=e, stop=e * .99, target=e * 1.02, cost_r=.1)
        now = d.index[101] + pd.Timedelta(hours=1.5)
        journal.record([t], now + pd.Timedelta(hours=9))                # stale bar: no hindsight entries
        self.assertEqual(journal.history("1h")["open"], 0)
        journal.record([t, {**t, "bar_time": d.index[101].isoformat()}, {**t, "direction": "NEUTRAL", "symbol": "N"}],
                       now - pd.Timedelta(hours=1))
        self.assertEqual(journal.history("1h")["open"], 1)
        with mock.patch.object(journal, "fetch", return_value=(d, "USD")):
            journal.settle("1h")
        h = journal.history("1h")
        self.assertEqual((h["open"], h["closed"]), (0, 1))


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import main
        cls.main, cls.c = main, TestClient(main.app)

    def setUp(self):
        self.main._hits.clear()

    def test_bad_input(self):
        with mock.patch("routes.analyze.bundle", return_value={}):
            for q in ("capital=-1", "risk=50", "currency=XXX", "asset=foo", "timeframe=5s"):
                self.assertEqual(self.c.get(f"/api/analyze?{q}").status_code, 422, q)
            self.assertEqual(self.c.get("/api/analyze/<script>").status_code, 422)

    def test_detail_matches_list(self):
        import routes.analyze as a
        row = dict(symbol="EURUSD=X", timeframe="1h", asset="forex", direction="NEUTRAL", trade_score=1,
                   bar_time=pd.Timestamp.now(tz="UTC").isoformat(), p_win=.31)
        snap = {"expires": 9e12, "trades": [row], "missing": [], "generated_at": "x"}
        with mock.patch.dict(a._snap, {"1h": snap}), mock.patch.object(a, "bundle", return_value={}):
            one = self.c.get("/api/analyze/EURUSD=X").json()
            many = self.c.get("/api/analyze").json()["all_trades"][0]
        self.assertEqual(one["p_win"], many["p_win"])

    def test_untrained_is_503(self):
        with mock.patch("routes.analyze.bundle", return_value=None):
            self.assertEqual(self.c.get("/api/analyze").status_code, 503)

    def test_train_needs_token(self):
        self.assertEqual(self.c.post("/api/train").status_code, 403)
        self.assertEqual(self.c.post("/api/train", headers={"X-Admin-Token": "x"}).status_code, 403)

    def test_rate_limit(self):
        codes = [self.c.get("/api/symbols").status_code for _ in range(self.main.RATE_LIMIT + 1)]
        self.assertEqual(codes[-1], 429)


if __name__ == "__main__":
    unittest.main()
