# Option Fair Value Backend (Pricing Math)

Pricing math modules for the Option Fair Value Dashboard.

## Scope

This package contains ONLY the pricing math + tests:
- Black-Scholes-Merton closed-form European pricer with analytic Greeks
- Cox-Ross-Rubinstein binomial tree (European + American)
- Monte Carlo (European with antithetic variates; American via Longstaff-Schwartz)
- Finite-difference Greeks wrapper
- Fair-value range engine (Latin-hypercube sampling across vol/spot/rate/T, all three models)
- Black-76 pricer + implied-vol solver (`app/pricing/implied_vol.py`)
- IV relative-value analysis (`app/analysis/`): parity-implied forward, robust
  smile fit, rich/cheap flagging with liquidity + price-materiality gates

It does NOT include the FastAPI app, data layer, or frontend. Other agents own those.

## Layout

```
backend/
  pyproject.toml
  app/
    __init__.py
    pricing/
      __init__.py        # re-exports
      black_scholes.py   # OptionInputs, PricerResult, price_bs
      binomial.py
      monte_carlo.py
      ranges.py
      greeks.py
  tests/
```

## Install

```
cd backend
pip install -e ".[dev]"
```

## Test

```
pytest -v
```

## IV mispricing analysis

`GET /analysis/{symbol}?expiry=YYYY-MM-DD` screens one expiry's chain for
relative-value outliers: it infers the implied forward from put-call parity,
solves Black-76 IVs from OTM mids (Yahoo's IV column is display-only fallback),
fits a robust vega-weighted quadratic smile in log-moneyness within a
±4-stdev moneyness band, and flags contracts whose IV sits ≥ 2 robust sigmas
off the fit — gated on liquidity (bid > 0, spread ≤ 25%, OI/volume minimums)
and price materiality (fitted value outside the quoted bid-ask). Optional
query params: `z_threshold`, `max_rel_spread`, `min_open_interest`,
`min_volume`. Flags are screening signals on ~15-min-delayed data, not
arbitrage.

If FRED is not configured the endpoint uses `OFV_FALLBACK_RATE` (default
`0.04`) instead of failing, and reports `rate_source: "fallback"`.

## Background mispricing scanner

With `OFV_SCANNER_ENABLED=1`, a background task sweeps `OFV_SCANNER_WATCHLIST`
(default `SPY,QQQ,AAPL,NVDA`) across up to `OFV_SCANNER_MAX_EXPIRIES` near
expiries every `OFV_SCANNER_INTERVAL` seconds during US market hours, running
the same analysis as `/analysis`. A contract becomes an **active alert** only
after staying flagged for `OFV_SCANNER_PERSISTENCE` consecutive sweeps
(filters one-tick quote glitches); alerts resolve automatically when the
contract prices back onto its smile. State survives restarts via the cache.

* `GET /alerts` — active/pending/resolved alerts + scanner status
* `POST /alerts/scan` — run a sweep immediately (works after hours too)

## Input contract

All pricers take a frozen `OptionInputs` dataclass and return a frozen
`PricerResult` (price + Greeks). Theta is per calendar day, vega per 1% vol,
rho per 1% rate. See `app/pricing/black_scholes.py` for the definitions.

## Deviations from spec

- `requires-python` was relaxed from `>=3.11` to `>=3.10` so the package
  installs on the available interpreter (3.10.11). All annotations use
  `from __future__ import annotations` so `float | None` syntax is safe.
- The spec's reference values for Black-Scholes **theta** (`-0.0104`) and
  **rho** (`0.0532`) are inconsistent with the explicit formulas the spec
  itself provides. The formulas (`theta = annual/365` with the full rate
  term, and `rho = K*T*exp(-rT)*N(d2)/100` per 1%) yield
  `theta ≈ -0.01758/day` and `rho ≈ 0.5323` per 1% for the ATM call
  (S=K=100, T=1, r=0.05, σ=0.20). The reference theta `-0.0104` corresponds
  to dropping the `r*K*exp(-rT)*N(d2)` term, and the reference rho `0.0532`
  corresponds to an extra `/10` (i.e., per 10bp). The implementation follows
  the explicit formulas in the spec; the tests assert the formula-consistent
  values.
- Monte-Carlo and binomial Greeks use the generic finite-difference wrapper
  (`compute_greeks_fd`) with a price-only core to avoid recomputing Greeks
  recursively. The LHS range loop calls price-only cores (`_binomial_tree_price`,
  `_mc_price_only`) so it does not redundantly compute Greeks per LHS point.

