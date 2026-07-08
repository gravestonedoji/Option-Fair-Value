"""Black-76 pricing and implied-volatility solving.

Black-76 prices off the forward, which lets callers absorb dividends into a
parity-implied forward instead of estimating a dividend yield. The solver
returns a status instead of raising so chain-wide sweeps can record why a
quote had no solvable IV (stale/crossed quotes routinely violate bounds).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from app.pricing.black_scholes import OptionType

# Quotes at exactly a no-arb bound are unsolvable; tolerance keeps float noise
# on the bound itself from flipping the classification.
_BOUND_EPS = 1e-12


@dataclass(frozen=True)
class IVResult:
    iv: Optional[float]
    status: str  # "ok" | "below_intrinsic" | "above_max" | "no_convergence" | "bad_inputs"
    vega: Optional[float] = None  # Black-76 vega per 1.00 vol at the solution


def black76_price(
    forward: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    sigma: float,
    option_type: OptionType,
) -> float:
    from scipy.stats import norm

    F = float(forward)
    K = float(strike)
    T = float(time_to_expiry)
    r = float(rate)

    discount = math.exp(-r * T)
    if T <= 0.0 or sigma <= 0.0 or F <= 0.0 or K <= 0.0:
        if option_type is OptionType.CALL:
            return discount * max(F - K, 0.0)
        return discount * max(K - F, 0.0)

    sqrtT = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT

    if option_type is OptionType.CALL:
        return float(discount * (F * norm.cdf(d1) - K * norm.cdf(d2)))
    return float(discount * (K * norm.cdf(-d2) - F * norm.cdf(-d1)))


def black76_vega(
    forward: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    sigma: float,
) -> float:
    from scipy.stats import norm

    F = float(forward)
    K = float(strike)
    T = float(time_to_expiry)

    if T <= 0.0 or sigma <= 0.0 or F <= 0.0 or K <= 0.0:
        return 0.0

    sqrtT = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * sqrtT)
    return float(math.exp(-float(rate) * T) * F * norm.pdf(d1) * sqrtT)


def implied_vol_black76(
    price: float,
    forward: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    option_type: OptionType,
    lo: float = 1e-4,
    hi: float = 5.0,
) -> IVResult:
    from scipy.optimize import brentq

    F = float(forward)
    K = float(strike)
    T = float(time_to_expiry)
    r = float(rate)
    p = float(price)

    if (
        T <= 0.0
        or F <= 0.0
        or K <= 0.0
        or p <= 0.0
        or not all(math.isfinite(x) for x in (F, K, T, r, p))
    ):
        return IVResult(iv=None, status="bad_inputs")

    discount = math.exp(-r * T)
    if option_type is OptionType.CALL:
        lower = discount * max(F - K, 0.0)
        upper = discount * F
    else:
        lower = discount * max(K - F, 0.0)
        upper = discount * K

    if p <= lower + _BOUND_EPS:
        return IVResult(iv=None, status="below_intrinsic")
    if p >= upper - _BOUND_EPS:
        return IVResult(iv=None, status="above_max")

    def objective(sigma: float) -> float:
        return black76_price(F, K, T, r, sigma, option_type) - p

    f_lo = objective(lo)
    f_hi = objective(hi)
    # Bounds above guarantee a root exists in (0, inf); it can still fall
    # outside [lo, hi] for quotes with negligible or enormous time value.
    if f_lo > 0.0 or f_hi < 0.0 or not (math.isfinite(f_lo) and math.isfinite(f_hi)):
        return IVResult(iv=None, status="no_convergence")

    try:
        iv = brentq(objective, lo, hi, xtol=1e-8, maxiter=100)
    except (ValueError, RuntimeError):
        return IVResult(iv=None, status="no_convergence")

    return IVResult(
        iv=float(iv),
        status="ok",
        vega=float(black76_vega(F, K, T, r, iv)),
    )
