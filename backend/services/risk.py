"""Trade geometry, outcome simulation and position sizing."""
import math

import numpy as np
import pandas as pd

from config import ATR_STOP, ATR_TARGET, HORIZON, MAX_LEVERAGE, RISK_REWARD


def levels(entry: float, atr: float, side: int):
    return entry - side * ATR_STOP * atr, entry + side * ATR_TARGET * atr


def outcomes(df: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    """R-multiple of a long and a short opened at every bar's close.

    Stop wins ties inside a bar (pessimistic); gaps through the stop fill at the open.
    Rows without a full `horizon` of future bars are left NaN so they never become labels.
    """
    o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    risk = ATR_STOP * df["atr"].to_numpy(float)
    n, out = len(df), {}
    for name, s in (("long", 1), ("short", -1)):
        stop, target = levels(c, df["atr"].to_numpy(float), s)
        r = np.full(n, np.nan)
        bars = np.full(n, horizon)
        win = np.zeros(n, bool)
        live = np.arange(n) + horizon < n
        for k in range(1, horizon + 1):
            i = np.flatnonzero(live)
            if not len(i):
                break
            j = i + k
            adverse, favour = (l[j], h[j]) if s == 1 else (h[j], l[j])
            gap_win = s * (o[j] - target[i]) >= 0
            stopped = ~gap_win & (s * (adverse - stop[i]) <= 0)
            won = gap_win | (~stopped & (s * (favour - target[i]) >= 0))
            fill = np.where(s * (o[j] - stop[i]) < 0, o[j], stop[i])
            r[i[stopped]] = (s * (fill - c[i]) / risk[i])[stopped]
            r[i[won]] = RISK_REWARD
            win[i[won]] = True
            hit = i[stopped | won]
            bars[hit] = k
            live[hit] = False
        i = np.flatnonzero(live)                          # timed out
        r[i] = s * (c[i + horizon] - c[i]) / risk[i]
        out[f"r_{name}"], out[f"win_{name}"], out[f"bars_{name}"] = r, win, bars
    return pd.DataFrame(out, index=df.index)


def resolve(bars: pd.DataFrame, entry, stop, target, side, horizon: int = HORIZON):
    """Scalar twin of `outcomes` for one live signal. -> (status, r) or None if still open."""
    risk = abs(entry - stop)
    for k, (o, h, l, c) in enumerate(bars[["Open", "High", "Low", "Close"]].itertuples(index=False), 1):
        adverse, favour = (l, h) if side == 1 else (h, l)
        if side * (o - target) >= 0:
            return "win", RISK_REWARD
        if side * (adverse - stop) <= 0:
            fill = o if side * (o - stop) < 0 else stop
            return "loss", side * (fill - entry) / risk
        if side * (favour - target) >= 0:
            return "win", RISK_REWARD
        if k >= horizon:
            return "timeout", side * (c - entry) / risk
    return None


def size_multiplier(p_win: float, p_breakeven: float) -> float:
    """ML multiplier M_size in [0.5, 1]. Never scales risk above the user's limit."""
    return float(np.clip(0.5 + 5 * (p_win - p_breakeven), 0.5, 1.0))


def position(entry, stop, asset, capital, risk_pct, fx, mult=1.0) -> dict:
    """Units so that hitting the stop loses `risk_pct`% of capital.

    `fx` = value of one unit of the instrument's quote currency in account currency.
    """
    per_unit = abs(entry - stop) * fx
    units = capital * risk_pct / 100 * mult / per_unit
    cap = capital * MAX_LEVERAGE.get(asset, 5) / (entry * fx)
    capped = units > cap
    units = min(units, cap)
    units = math.floor(units) if asset in ("forex", "stock") else math.floor(units * 1e6) / 1e6
    return {
        "units": units, "capped": capped,
        "notional": round(units * entry * fx, 2),
        "risk_amount": round(units * per_unit, 2),
        "leverage": round(units * entry * fx / capital, 2),
    }
