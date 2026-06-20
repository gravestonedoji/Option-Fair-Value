from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class ExerciseStyle(str, Enum):
    EUROPEAN = "european"
    AMERICAN = "american"


@dataclass(frozen=True)
class OptionInputs:
    spot: float
    strike: float
    time_to_expiry: float
    risk_free_rate: float
    volatility: float
    dividend_yield: float = 0.0
    option_type: OptionType = OptionType.CALL
    style: ExerciseStyle = ExerciseStyle.EUROPEAN


@dataclass(frozen=True)
class PricerResult:
    price: float
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None


def _intrinsic(inputs: OptionInputs) -> PricerResult:
    if inputs.option_type is OptionType.CALL:
        intrinsic = max(inputs.spot - inputs.strike, 0.0)
    else:
        intrinsic = max(inputs.strike - inputs.spot, 0.0)
    return PricerResult(price=intrinsic, delta=None, gamma=None, theta=None, vega=None, rho=None)


def price_bs(inputs: OptionInputs) -> PricerResult:
    import math

    from scipy.stats import norm

    S = float(inputs.spot)
    K = float(inputs.strike)
    T = float(inputs.time_to_expiry)
    r = float(inputs.risk_free_rate)
    q = float(inputs.dividend_yield)
    sigma = float(inputs.volatility)

    if T <= 0.0 or sigma <= 0.0 or S <= 0.0 or K <= 0.0:
        return _intrinsic(inputs)

    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT

    discount_r = math.exp(-r * T)
    discount_q = math.exp(-q * T)
    pdf_d1 = norm.pdf(d1)
    Nd1 = norm.cdf(d1)
    Nd2 = norm.cdf(d2)
    Nminus_d1 = norm.cdf(-d1)
    Nminus_d2 = norm.cdf(-d2)

    is_call = inputs.option_type is OptionType.CALL

    if is_call:
        price = S * discount_q * Nd1 - K * discount_r * Nd2
        delta = discount_q * Nd1
    else:
        price = K * discount_r * Nminus_d2 - S * discount_q * Nminus_d1
        delta = discount_q * (Nd1 - 1.0)

    gamma = discount_q * pdf_d1 / (S * sigma * sqrtT)
    vega_raw = S * discount_q * pdf_d1 * sqrtT
    vega = vega_raw / 100.0

    common_theta_term = -S * discount_q * pdf_d1 * sigma / (2.0 * sqrtT)
    if is_call:
        theta_annual = common_theta_term - r * K * discount_r * Nd2 + q * S * discount_q * Nd1
    else:
        theta_annual = common_theta_term + r * K * discount_r * Nminus_d2 - q * S * discount_q * Nminus_d1
    theta = theta_annual / 365.0

    if is_call:
        rho = K * T * discount_r * Nd2 / 100.0
    else:
        rho = -K * T * discount_r * Nminus_d2 / 100.0

    return PricerResult(
        price=float(price),
        delta=float(delta),
        gamma=float(gamma),
        theta=float(theta),
        vega=float(vega),
        rho=float(rho),
    )
