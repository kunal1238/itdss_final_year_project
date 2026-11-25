"""Technical indicators and scale-free ML features.

Every feature is a ratio (ATR units, percent-of-range, ...), so one model can be
trained on and applied to instruments with completely different price levels.
"""
import numpy as np
import pandas as pd

from config import ATR_PERIOD, EMA_FAST, EMA_SLOW, RSI_PERIOD, WILLIAMS_R_PERIOD

FEATURES = ["williams_r", "rsi", "atr_rel", "vol_rel", "ema_spread",
            "ema_slope", "dist_fast", "mom_10", "mom_50"]
EPS = 1e-12


def atr(df, n=ATR_PERIOD):
    prev = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()      # Wilder smoothing


def williams_r(df, n=WILLIAMS_R_PERIOD):
    hh, ll = df["High"].rolling(n).max(), df["Low"].rolling(n).min()
    return -100 * (hh - df["Close"]) / (hh - ll + EPS)


def rsi(close, n=RSI_PERIOD):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 * up / (up + dn + EPS)


def compute(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["Close"]
    df["ema_fast"] = c.ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = c.ewm(span=EMA_SLOW, adjust=False).mean()
    df["atr"] = atr(df)
    a = df["atr"] + EPS
    ret = c.pct_change()

    df["williams_r"] = williams_r(df)
    df["rsi"] = rsi(c)
    df["atr_rel"] = df["atr"] / (df["atr"].rolling(200).mean() + EPS)
    df["vol_rel"] = ret.rolling(20).std() / (ret.rolling(100).std() + EPS)
    df["ema_spread"] = (df["ema_fast"] - df["ema_slow"]) / a
    df["ema_slope"] = df["ema_fast"].diff(10) / a
    df["dist_fast"] = (c - df["ema_fast"]) / a
    df["mom_10"] = c.diff(10) / a
    df["mom_50"] = c.diff(50) / a

    df = df.iloc[EMA_SLOW:]                               # EMA warm-up
    df = df[df["atr"] > df["Close"] * 1e-7]               # dead/flat data
    return df.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURES)
