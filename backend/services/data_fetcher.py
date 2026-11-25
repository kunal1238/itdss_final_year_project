"""Market data from Yahoo Finance: cleaned, closed bars only, cached."""
import threading
import time
from collections import OrderedDict

import pandas as pd
import yfinance as yf

from config import TIMEFRAMES

_MAX = 400
_cache: OrderedDict = OrderedDict()   # (symbol, tf, period) -> (expires, df, currency)
_locks: dict = {}
_guard = threading.Lock()


def clean(df: pd.DataFrame, minutes: int, now=None) -> pd.DataFrame:
    """OHLCV, UTC, sorted, de-duplicated, sane, and without the still-forming bar."""
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    local = df.index
    df.index = df.index.tz_convert("UTC")
    now = now or pd.Timestamp.now(tz="UTC")
    # A daily bar is stamped at local midnight; treat it as closed once that day is over.
    closed = (local + pd.Timedelta(minutes=minutes)).tz_convert("UTC") <= now
    df = df[closed]
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    ok = (df[["Open", "High", "Low", "Close"]] > 0).all(axis=1) & (df["High"] >= df["Low"])
    df = df[ok]
    df["High"] = df[["Open", "High", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "Low", "Close"]].min(axis=1)
    return df


def _download(symbol, tf, period):
    err = None
    for attempt in range(2):
        try:
            t = yf.Ticker(symbol)
            df = t.history(period=period, interval=tf, auto_adjust=True)
            if df is not None and not df.empty:
                cur = (t.history_metadata or {}).get("currency") or "USD"
                return clean(df, TIMEFRAMES[tf]["minutes"]), cur
        except Exception as e:  # network / Yahoo errors
            err = e
        time.sleep(0.5 * (attempt + 1))
    if err:
        print(f"[data] {symbol} {tf}: {err}")
    return None


def fetch(symbol: str, tf: str = "1h", period: str | None = None):
    """Return (df, quote_currency) or None. Serves stale data if Yahoo is down."""
    period = period or TIMEFRAMES[tf]["live"]
    key = (symbol, tf, period)
    with _guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:                                   # single-flight per key
        hit = _cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1], hit[2]
        got = _download(symbol, tf, period)
        if got is None:
            return (hit[1], hit[2]) if hit else None
        with _guard:
            _cache[key] = (time.time() + TIMEFRAMES[tf]["ttl"], *got)
            _cache.move_to_end(key)
            while len(_cache) > _MAX:
                old, _ = _cache.popitem(last=False)
                _locks.pop(old, None)
        return got


# Yahoo quotes some exchanges in hundredths of the currency.
_MINOR = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}
_fx: dict = {}


def fx_rate(src: str, dst: str) -> float | None:
    """Value of one unit of `src` in `dst`; None if it cannot be determined."""
    scale = 1.0
    if src in _MINOR:
        src, scale = _MINOR[src], 0.01
    if src == dst:
        return scale
    hit = _fx.get((src, dst))
    if hit and hit[0] > time.time():
        return hit[1] * scale
    for pair, inverse in ((f"{src}{dst}=X", False), (f"{dst}{src}=X", True)):
        got = fetch(pair, "1d", "1mo")
        if got is not None and len(got[0]):
            px = float(got[0]["Close"].iloc[-1])
            rate = 1 / px if inverse else px
            _fx[(src, dst)] = (time.time() + 3600, rate)
            return rate * scale
    return None
