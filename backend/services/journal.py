"""Append-only record of every live signal and what actually happened next."""
import sqlite3
import threading
from contextlib import closing

import pandas as pd

from config import DATA_DIR, TIMEFRAMES
from services.data_fetcher import fetch
from services.risk import resolve

_lock = threading.Lock()


def _db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA_DIR / "journal.db", timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS signals(
        symbol TEXT, timeframe TEXT, bar_time TEXT, side INT, p_win REAL, entry REAL, stop REAL,
        target REAL, cost_r REAL, status TEXT DEFAULT 'open', r REAL,
        PRIMARY KEY(symbol, timeframe, bar_time))""")
    return db


def bars_old(t, now=None):
    """Bars elapsed since the signal's bar closed."""
    now = now or pd.Timestamp.now(tz="UTC")
    bar = pd.Timedelta(minutes=TIMEFRAMES[t["timeframe"]]["minutes"])
    return (now - (pd.Timestamp(t["bar_time"]) + bar)) / bar


def record(trades, now=None):
    """Log new signals; skip a symbol that already has an open one.

    Only bars that closed within the last bar length are logged: an older one could be "entered"
    with hindsight, at a price that is no longer available.
    """
    trades = [t for t in trades if bars_old(t, now) <= 1]
    with _lock, closing(_db()) as db, db:
        for t in trades:
            if t["direction"] == "NEUTRAL":
                continue
            db.execute("""INSERT OR IGNORE INTO signals(symbol,timeframe,bar_time,side,p_win,entry,stop,target,cost_r)
                SELECT ?,?,?,?,?,?,?,?,? WHERE NOT EXISTS
                (SELECT 1 FROM signals WHERE symbol=? AND timeframe=? AND status='open')""",
                       (t["symbol"], t["timeframe"], t["bar_time"], t["side"], t["p_win"], t["entry"],
                        t["stop"], t["target"], t["cost_r"], t["symbol"], t["timeframe"]))


def settle(tf):
    with closing(_db()) as db:
        rows = db.execute("SELECT * FROM signals WHERE status='open' AND timeframe=?", (tf,)).fetchall()
    for s in rows:
        got = fetch(s["symbol"], tf)
        if got is None:
            continue
        bars = got[0][got[0].index > pd.Timestamp(s["bar_time"])]
        res = resolve(bars, s["entry"], s["stop"], s["target"], s["side"])
        if res:
            with _lock, closing(_db()) as db, db:
                db.execute("UPDATE signals SET status=?, r=? WHERE symbol=? AND timeframe=? AND bar_time=?",
                           (res[0], res[1] - s["cost_r"], s["symbol"], tf, s["bar_time"]))


def history(tf, limit=100):
    with closing(_db()) as db:
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM signals WHERE timeframe=? ORDER BY bar_time DESC LIMIT ?", (tf, limit))]
        n, wins, avg = db.execute("""SELECT COUNT(*), SUM(r>0), AVG(r) FROM signals
                                     WHERE timeframe=? AND status!='open'""", (tf,)).fetchone()
        open_ = db.execute("SELECT COUNT(*) FROM signals WHERE timeframe=? AND status='open'", (tf,)).fetchone()[0]
    return {"closed": n, "open": open_, "win_rate": (wins / n) if n else None, "avg_r": avg, "signals": rows}
