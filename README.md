# Option Fair Value Dashboard

An interactive dashboard for the **fair value range** of US equity options.
Pick a symbol → expiry → strike/type from the options chain, and the panel
shows a **range of fair values** (min · P5 · median · P95 · max) from three
pricing models side-by-side, plus Greeks — all computed under uncertainty
over the inputs (IV, spot, rate, time-to-expiry).

## How the "range" works

The range is **uncertainty over inputs**, not a price distribution. Given
base inputs (spot, IV, rate, DTE from market data) and uncertainty bands
(±% on IV, ±% on spot, ±bps on rate, ±days on DTE), the backend draws
200 Latin-hypercube samples across the 4-D hyper-rectangle and prices the
option at each point with all three models. The resulting 200 prices per
model give the min/P5/median/P95/max you see in the UI. Wider bands →
wider fair-value range; the sliders let you tune the bands live.

## Models

| Model | Notes |
|---|---|
| **Black-Scholes** | Closed-form European with continuous dividend yield. Labeled as European approximation in the UI (US equity options are American). |
| **Binomial (CRR)** | 200-step Cox-Ross-Rubinstein tree, American-aware (early-exercise check). |
| **Monte Carlo** | 50k antithetic GBM paths; American via Longstaff-Schwartz. |

All three run for every request: 200 LHS points × 50k MC paths = ~10M
simulations, ~1-2s per request. Greeks are computed at the base inputs
(analytic for BS, finite-difference for binomial/MC).

## Architecture

```
backend/   FastAPI + pricing math + data layer (Python 3.10+)
  app/pricing/    BS, binomial, Monte Carlo, fair-value range engine, Greeks
  app/data/       yfinance client, FRED rate client, SQLite TTL cache
  app/api/        /expiries, /chain, /fairvalue routes
  app/main.py     FastAPI app, CORS, lifespan
  tests/          41 passing, 4 network-skipped
frontend/  React 18 + Vite + TypeScript + Tailwind
  src/api/        axios client + react-query hooks
  src/components/ SymbolSearch, ExpirySelector, OptionsChain,
                  FairValuePanel (InputSliders, RangeChart,
                  ModelComparison, GreeksTable)
```

## Data sources

- **Options chains + spot**: yfinance (free, no key, delayed). Cached 60s.
- **Risk-free rate**: FRED 3-month Treasury constant maturity (`DGS3MO`).
  Requires `FRED_API_KEY`. Cached 1h.
- **Dividend yield**: defaults to 0; override via the API `overrides` field.
- All responses cached in SQLite at `~/.option_fair_value/cache.sqlite`.

## Quick start

### 1. Backend

```powershell
cd backend
python -m pip install -e ".[dev]"

# Set your FRED API key (get one free at https://fredaccount.stlouisfed.org)
$env:FRED_API_KEY = "your_key_here"

python -m uvicorn app.main:app --reload --port 8000
```

API docs at http://127.0.0.1:8000/docs. Health at `/health`
(`fred_enabled` shows whether the key was loaded).

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### Or: start both at once

```powershell
.\start-dev.ps1
```

(Stops both servers with `.\stop-dev.ps1`, or close the windows.)

## API

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| GET | `/expiries/{symbol}` | — | `{ symbol, expiries: [...], cached_at }` |
| GET | `/chain/{symbol}?expiry=YYYY-MM-DD` | — | `{ symbol, expiry, spot, rows: [...], cached_at }` |
| POST | `/fairvalue` | `{ symbol, expiry, strike, type, bands, overrides? }` | `{ models: {black_scholes, binomial, monte_carlo}, bands, base_inputs, base_results, samples }` |

`overrides` is optional; any of `spot`, `volatility`, `risk_free_rate`,
`dividend_yield`, `time_to_expiry`, `strike`, `option_type`, `style` can be
set to bypass the market-derived value. If `risk_free_rate` is overridden,
FRED is not called (useful for testing without a key).

## Tests

```powershell
cd backend
pytest -v
```

Network tests (yfinance, FRED) are skipped unless `OFV_RUN_NETWORK_TESTS=1`
(and `FRED_API_KEY` is set for the FRED test).

## Tech

- **Backend**: Python 3.10+, FastAPI, Pydantic v2, numpy, scipy, yfinance,
  httpx, SQLite.
- **Frontend**: React 18, Vite 5, TypeScript 5.4, TanStack Query 5, axios,
  Tailwind CSS 3, lucide-react.

## Notes / limitations

- yfinance data is delayed (~15 min) and rate-limited; the SQLite cache
  mitigates this.
- Default bands (±20% IV, ±5% spot, ±50bps, ±2d) are wide for very
  short-dated options (a ±5% spot move in 2 days is huge). Tune via the
  sliders.
- BS is labeled "European approximation" since US equity options are
  American; the binomial and Monte Carlo models handle early exercise.
- Dividend yield defaults to 0; supply via `overrides.dividend_yield` for
  dividend-paying underlyings if you want BS/binomial to reflect it.
