# ITDSS: Intelligent Trading Decision Support System

Explainable, risk-first market analysis for 37 instruments (forex, crypto, indices, commodities, stocks)
plus any Yahoo Finance symbol. It places no orders.

> **Educational research tool, not financial advice.** In walk-forward testing the current model has
> **no proven edge** over a no-skill baseline. The app says so on every page. See [docs/RESULTS.md](docs/RESULTS.md).

## Run

```bash
# backend (tested on Python 3.12)
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --port 8000
# frontend
cd frontend && npm ci && npm run dev            # http://localhost:5173
```

One container: `docker build -t itdss . && docker run -p 8000:8000 -v itdss:/app/backend/data itdss`

| Task | Command (in `backend/`) |
|---|---|
| Test | `.venv/bin/python -m unittest` |
| Retrain and re-evaluate | `.venv/bin/python train.py` |

| Variable | Default | Meaning |
|---|---|---|
| `ITDSS_ADMIN_TOKEN` | empty (retraining over HTTP disabled) | Secret for `POST /api/train` |
| `ITDSS_ORIGINS` | localhost | Allowed CORS origins, comma separated |
| `ITDSS_RATE_LIMIT` | 60 | API requests per minute per IP |
| `ITDSS_DATA_DIR` | `backend/data` | Signal journal location |
| `ITDSS_BACKGROUND` | 1 | Refresh in the background |

## How a signal is made

1. **Data:** closed bars only, cleaned, cached.
2. **Features:** nine scale-free ratios, so one model works across price levels.
3. **Label (triple barrier):** BUY if a long reaches +3 ATR before -1.5 ATR within 24 bars, SELL for the mirror
   case, otherwise NEUTRAL. Inside one bar the stop wins ties; gaps fill at the open.
4. **Model:** Random Forest, Platt-calibrated on the newest 20% of training data.
5. **Decision:** trade only if `P_win*RR + (1-P_win)*avg_nonwin - cost > 0`.
6. **Rank:** `P_win * RR / relative volatility`. Old bars are never recommended.
7. **Size:** fixed-fraction risk, converted to the account currency, capped by leverage.
8. **Journal:** live signals are logged when issued and settled later.

API documentation: `/docs` on the backend.
