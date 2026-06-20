from __future__ import annotations

from typing import Callable

from app.pricing.black_scholes import OptionInputs, PricerResult


def compute_greeks_fd(
    pricer: Callable[[OptionInputs], float],
    inputs: OptionInputs,
    spot_bump_rel: float = 0.01,
    vol_bump: float = 0.001,
    rate_bump: float = 0.0001,
    theta_dt_years: float = 1.0 / 365.0,
) -> PricerResult:
    S = inputs.spot
    h_s = spot_bump_rel * S

    base = pricer(inputs)

    up_inputs = _replace(inputs, spot=S + h_s)
    down_inputs = _replace(inputs, spot=S - h_s)
    p_up = pricer(up_inputs)
    p_down = pricer(down_inputs)

    delta = (p_up - p_down) / (2.0 * h_s)
    gamma = (p_up - 2.0 * base + p_down) / (h_s * h_s)

    vol_up = _replace(inputs, volatility=inputs.volatility + vol_bump)
    vol_down = _replace(inputs, volatility=inputs.volatility - vol_bump)
    vega_raw = (pricer(vol_up) - pricer(vol_down)) / (2.0 * vol_bump)
    vega = vega_raw / 100.0

    rate_up = _replace(inputs, risk_free_rate=inputs.risk_free_rate + rate_bump)
    rate_down = _replace(inputs, risk_free_rate=inputs.risk_free_rate - rate_bump)
    rho_raw = (pricer(rate_up) - pricer(rate_down)) / (2.0 * rate_bump)
    rho = rho_raw / 100.0

    if inputs.time_to_expiry > theta_dt_years:
        t_inputs = _replace(inputs, time_to_expiry=inputs.time_to_expiry - theta_dt_years)
        theta_annual = (pricer(t_inputs) - base) / theta_dt_years
    else:
        theta_annual = 0.0
    theta = theta_annual / 365.0

    return PricerResult(
        price=float(base),
        delta=float(delta),
        gamma=float(gamma),
        theta=float(theta),
        vega=float(vega),
        rho=float(rho),
    )


def _replace(inputs: OptionInputs, **changes) -> OptionInputs:
    from dataclasses import replace

    return replace(inputs, **changes)
