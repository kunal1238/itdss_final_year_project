"""Train and evaluate: python train.py [1h 1d]"""
import sys

from config import TIMEFRAMES
from services.training import train

if __name__ == "__main__":
    for tf in sys.argv[1:] or TIMEFRAMES:
        rep = train(tf)
        for name, r in rep["results"].items():
            print(f"{name:18}", {k: r.get(k) for k in
                  ("accuracy", "balanced_accuracy", "log_loss", "trades", "win_rate", "avg_r", "ci",
                   "profit_factor", "sharpe", "max_drawdown")})
