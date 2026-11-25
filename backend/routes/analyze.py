"""Signals, ranking, search, track record."""
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Literal

import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

from config import ASSET_CLASS, CURRENCIES, LABELS, MAX_AGE_H, MIN_BARS, TIMEFRAMES, TOP_N, UNIVERSE
from services import journal
from services.data_fetcher import fetch, fx_rate
from services.indicators import compute
from services.ml_scorer import bundle, score
from services.risk import position, size_multiplier

router = APIRouter(tags=["Analyze"])
TF = Literal["1h", "1d"]
SYMBOL = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^&]{0,19}$")
_snap: dict = {}
_locks = {tf: threading.Lock() for tf in TIMEFRAMES}


def analyze_one(symbol, tf):
    got = fetch(symbol, tf)
    if got is None or len(got[0]) < MIN_BARS:
        return None
    return score(compute(got[0]), symbol, tf, got[1])


def snapshot(tf):
    """Scores for the whole universe. Shared by all users; one refresh at a time."""
    hit = _snap.get(tf)
    if hit and hit["expires"] > time.time():
        return hit
    if hit and _locks[tf].locked():
        return hit                                         # serve slightly stale instead of queueing
    with _locks[tf]:
        hit = _snap.get(tf)
        if hit and hit["expires"] > time.time():
            return hit

        def safe(s):
            try:
                return analyze_one(s, tf)
            except Exception:
                traceback.print_exc()
                return None

        with ThreadPoolExecutor(8) as ex:
            trades = [t for t in ex.map(safe, ASSET_CLASS) if t]
        missing = sorted(set(ASSET_CLASS) - {t["symbol"] for t in trades})
        try:
            journal.settle(tf)
            journal.record(trades)
        except Exception:                                  # the journal must never break analysis
            traceback.print_exc()
        ttl = TIMEFRAMES[tf]["ttl"] if trades else 20      # retry soon when everything failed
        _snap[tf] = {"expires": time.time() + ttl, "trades": trades, "missing": missing,
                     "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        return _snap[tf]


def personalise(t, capital, risk, currency):
    """Add position sizing in the user's own currency."""
    age_h = journal.bars_old(t) * TIMEFRAMES[t["timeframe"]]["minutes"] / 60
    out = {**t, "position": None, "fresh": age_h <= MAX_AGE_H[t["timeframe"]]}
    if t["direction"] != "NEUTRAL" and t["asset"] != "index":     # an index level is not tradable itself
        fx = fx_rate(t["currency"], currency)
        if fx:
            m = size_multiplier(t["p_win"], t["p_breakeven"])
            out["position"] = {**position(t["entry"], t["stop"], t["asset"], capital, risk, fx, m),
                               "multiplier": round(m, 2), "currency": currency}
    return out


CAPITAL = Query(100_000, gt=0, le=1e12)
RISK = Query(1.0, gt=0, le=5, description="percent of capital risked per trade")
CURRENCY = Query("USD", pattern="^[A-Z]{3}$")


def _check(tf, currency):
    if currency not in CURRENCIES:
        raise HTTPException(422, "unsupported currency")
    if bundle(tf) is None:
        raise HTTPException(503, "model not trained yet: run `python train.py`")


@router.get("/analyze")
def analyze_all(timeframe: TF = "1h", asset: str | None = None, top: int = Query(TOP_N, ge=1, le=50),
                capital: float = CAPITAL, risk: float = RISK, currency: str = CURRENCY):
    _check(timeframe, currency)
    if asset and asset not in UNIVERSE:
        raise HTTPException(422, "unknown asset class")
    s = snapshot(timeframe)
    rows = [personalise(t, capital, risk, currency) for t in s["trades"] if not asset or t["asset"] == asset]
    rows.sort(key=lambda t: (t["direction"] == "NEUTRAL", not t["fresh"], -t["trade_score"]))
    return {"count": len(rows), "timeframe": timeframe, "generated_at": s["generated_at"],
            "missing": [m for m in s["missing"] if not asset or ASSET_CLASS[m] == asset],
            "top_trades": [t for t in rows if t["direction"] != "NEUTRAL" and t["fresh"]][:top], "all_trades": rows}


@router.get("/top-trades")
def top_trades(timeframe: TF = "1h", n: int = Query(TOP_N, ge=1, le=50), capital: float = CAPITAL,
               risk: float = RISK, currency: str = CURRENCY):
    return analyze_all(timeframe, None, n, capital, risk, currency)["top_trades"]


@router.get("/analyze/{symbol}")
def analyze_symbol(symbol: str, timeframe: TF = "1h", capital: float = CAPITAL, risk: float = RISK,
                   currency: str = CURRENCY):
    """Any Yahoo Finance symbol, e.g. /api/analyze/EURUSD=X or /api/analyze/INFY.NS"""
    _check(timeframe, currency)
    symbol = symbol.upper()
    if not SYMBOL.match(symbol):
        raise HTTPException(422, "invalid symbol")
    # Listed instruments come from the shared snapshot so a card and its details always agree.
    t = next((x for x in snapshot(timeframe)["trades"] if x["symbol"] == symbol), None) \
        if symbol in ASSET_CLASS else analyze_one(symbol, timeframe)
    if t is None:
        raise HTTPException(404, "no data, or not enough history, for this symbol")
    return {**personalise(t, capital, risk, currency), "in_universe": symbol in LABELS}


@router.get("/candles/{symbol}")
def candles(symbol: str, timeframe: TF = "1h", n: int = Query(150, ge=20, le=500)):
    symbol = symbol.upper()
    if not SYMBOL.match(symbol):
        raise HTTPException(422, "invalid symbol")
    got = fetch(symbol, timeframe)
    if got is None or len(got[0]) < MIN_BARS:
        raise HTTPException(404, "no data for this symbol")
    d = compute(got[0]).tail(n)
    return [{"t": i.isoformat(), "c": float(r.Close), "f": float(r.ema_fast), "s": float(r.ema_slow)}
            for i, r in d.iterrows()]


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=40)):
    try:
        quotes = yf.Search(q, max_results=10, news_count=0).quotes
    except Exception:
        raise HTTPException(502, "search is unavailable")
    return [{"symbol": x["symbol"], "name": x.get("shortname") or x.get("longname") or x["symbol"],
             "exchange": x.get("exchDisp", "")} for x in quotes if SYMBOL.match(x.get("symbol", ""))]


@router.get("/history")
def history(timeframe: TF = "1h"):
    return journal.history(timeframe)
