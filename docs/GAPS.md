# Gaps found in version 1, and their status

| # | Gap in v1 | Effect | Status |
|---|---|---|---|
| 1 | Score was P(price rises) for every direction | Strong SELLs ranked last | Fixed: win probability of the trade itself |
| 2 | NEUTRAL instruments shown as top trades, with stops and sizes | Advice where there was no signal | Fixed |
| 3 | Position size ignored quote currency | USD/JPY: 3,898 units instead of about 620,000 | Fixed |
| 4 | Raw ATR used as a feature; model fitted on one instrument | Meaningless on other price scales | Fixed: scale-free, pooled |
| 5 | Volume feature always zero for forex | Dead input | Removed |
| 6 | Unfinished rows labelled "did not rise" | Wrong labels | Fixed |
| 7 | Label unrelated to the stop and target shown | Score did not describe the trade | Fixed: triple barrier |
| 8 | No out-of-sample test, baselines or costs | 92% / 94.2% claims unverifiable | Fixed: purged walk-forward, 6 comparators |
| 9 | Probabilities uncalibrated | "70%" had no meaning | Fixed: Platt scaling, calibration plot |
| 10 | Still-forming bar used | Signals repaint | Fixed: closed bars only |
| 11 | Every visitor downloaded all data again | Slow, Yahoo rate limits | Fixed: shared cache |
| 12 | Settings, training and ranking endpoints, radar, explanations described in the paper but missing | Paper and code differ | Added |
| 13 | No record of outcomes | Could not be held to account | Added: signal journal |
| 14 | No input checks, rate limit or security headers; 3 high npm advisories | Unsafe to host | Fixed |
| 15 | Hard-coded localhost API; no tests, CI or container | Could not be deployed | Fixed |
| 16 | English, dark, desktop only; red/green | Excluded many users | 6 languages, RTL, mobile, light/dark, colour-blind safe |

## Still open

- **No predictive edge** (see RESULTS.md). More indicators will not fix this; new information might.
- **Data licence:** Yahoo data through yfinance is for personal use. A public service needs a licensed feed.
- **Regulation:** publishing signals can be regulated (for example SEBI in India). Take legal advice first.
- **Survivorship bias:** the stock and crypto list was chosen today, which flatters long results.
- **Not modelled:** overnight financing, market impact, correlation between open positions.
- **Costs are assumptions** per asset class, not broker quotes.
- **Walk-forward hyperparameters are fixed, not tuned** per window.
- **Explanations** use tree-path (Saabas) contributions of the uncalibrated forest, not exact SHAP values.
- **Translations** need review by native speakers.
- **Scale:** cache, rate limit and journal are per server. Several servers need Redis and PostgreSQL.
