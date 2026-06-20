# Option Fair Value Backend (Pricing Math)

Pricing math modules for the Option Fair Value Dashboard.

## Scope

This package contains ONLY the pricing math + tests:
- Black-Scholes-Merton closed-form European pricer with analytic Greeks
- Cox-Ross-Rubinstein binomial tree (European + American)
- Monte Carlo (European with antithetic variates; American via Longstaff-Schwartz)
- Finite-difference Greeks wrapper
- Fair-value range engine (Latin-hypercube sampling across vol/spot/rate/T, all three models)

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

