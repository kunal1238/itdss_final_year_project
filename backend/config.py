"""Central configuration for ITDSS."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "ml"
DATA_DIR = Path(os.getenv("ITDSS_DATA_DIR", BASE_DIR / "data"))

# asset class -> {Yahoo symbol: label}
# NOTE: stocks/crypto were picked today, so their history carries survivorship bias.
UNIVERSE = {
    "forex": {
        "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY",
        "AUDUSD=X": "AUD/USD", "USDCAD=X": "USD/CAD", "USDCHF=X": "USD/CHF",
        "NZDUSD=X": "NZD/USD", "EURGBP=X": "EUR/GBP", "EURJPY=X": "EUR/JPY",
        "USDINR=X": "USD/INR",
    },
    "crypto": {
        "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana",
        "XRP-USD": "XRP",
    },
    "index": {
        "^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^FTSE": "FTSE 100",
        "^GDAXI": "DAX", "^N225": "Nikkei 225", "^NSEI": "Nifty 50",
        "^HSI": "Hang Seng", "^BVSP": "Bovespa",
    },
    "commodity": {"GC=F": "Gold", "SI=F": "Silver", "CL=F": "Crude Oil"},
    "stock": {
        "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA",
        "RELIANCE.NS": "Reliance", "TCS.NS": "TCS", "HDFCBANK.NS": "HDFC Bank",
        "7203.T": "Toyota", "0700.HK": "Tencent", "ASML.AS": "ASML",
        "SHEL.L": "Shell", "NESN.SW": "Nestlé", "VALE3.SA": "Vale",
    },
}
LABELS = {s: n for g in UNIVERSE.values() for s, n in g.items()}
ASSET_CLASS = {s: c for c, g in UNIVERSE.items() for s in g}

# live = history needed to score now, train = history used to fit, ttl = cache seconds
TIMEFRAMES = {
    "1h": {"live": "6mo", "train": "2y", "ttl": 300, "minutes": 60},
    "1d": {"live": "3y", "train": "10y", "ttl": 1800, "minutes": 1440},
}

# A bar older than this (hours after it closed) means a shut market: shown, never recommended.
MAX_AGE_H = {"1h": 3, "1d": 76}

# Indicators
ATR_PERIOD = 14
WILLIAMS_R_PERIOD = 14
RSI_PERIOD = 14
EMA_FAST = 50
EMA_SLOW = 200
MIN_BARS = 420                  # warm-up for EMA200 + 200-bar ATR average
WILLIAMS_R_OVERSOLD = -80       # used only by the rule-based baseline
WILLIAMS_R_OVERBOUGHT = -20

# Trade geometry
ATR_STOP = 1.5
ATR_TARGET = 3.0
RISK_REWARD = ATR_TARGET / ATR_STOP
HORIZON = 24                    # bars a trade may stay open

# Assumed round-trip cost (spread + slippage + commission), fraction of price.
COST = {"forex": 0.00015, "crypto": 0.0015, "index": 0.0003, "commodity": 0.0004, "stock": 0.0010}
# Notional caps (modelled on ESMA retail limits).
MAX_LEVERAGE = {"forex": 30, "crypto": 2, "index": 20, "commodity": 10, "stock": 5}

RANDOM_SEED = 42
TOP_N = 5
BACKTEST_RISK = 0.01            # equity fraction risked per back-test trade

CURRENCIES = ["USD", "EUR", "GBP", "INR", "JPY", "CNY", "AUD", "CAD", "CHF", "BRL",
              "ZAR", "NGN", "AED", "SGD", "HKD", "KRW", "MXN", "IDR", "TRY", "SAR"]

# Deployment
ALLOWED_ORIGINS = [o for o in os.getenv(
    "ITDSS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if o]
ADMIN_TOKEN = os.getenv("ITDSS_ADMIN_TOKEN", "")        # empty = /api/train disabled
RATE_LIMIT = int(os.getenv("ITDSS_RATE_LIMIT", "60"))   # requests/min/IP
BACKGROUND = os.getenv("ITDSS_BACKGROUND", "1") == "1"
