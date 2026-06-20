from __future__ import annotations

import math

import numpy as np

from app.pricing.black_scholes import ExerciseStyle, OptionInputs, OptionType, PricerResult, _intrinsic
from app.pricing.greeks import compute_greeks_fd


def _binomial_tree_price(inputs: OptionInputs, steps: int) -> float:
    if steps < 2:
        steps = 2

    S = float(inputs.spot)
    K = float(inputs.strike)
    T = float(inputs.time_to_expiry)
    r = float(inputs.risk_free_rate)
    q = float(inputs.dividend_yield)
    sigma = float(inputs.volatility)
    is_call = inputs.option_type is OptionType.CALL

    if T <= 0.0 or sigma <= 0.0 or S <= 0.0 or K <= 0.0:
        return _intrinsic(inputs).price

    dt = T / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    p_up = (math.exp((r - q) * dt) - d) / (u - d)
    disc = math.exp(-r * dt)

    if not 0.0 < p_up < 1.0:
        p_up = max(min(p_up, 1.0 - 1e-12), 1e-12)

    i = np.arange(steps + 1)
    spot_nodes = S * (u ** i) * (d ** (steps - i))

    if is_call:
        payoff = np.maximum(spot_nodes - K, 0.0)
    else:
        payoff = np.maximum(K - spot_nodes, 0.0)

    V = payoff.copy()
    is_american = inputs.style is ExerciseStyle.AMERICAN

    for n in range(steps - 1, -1, -1):
        cont = disc * (p_up * V[1:] + (1.0 - p_up) * V[:-1])
        if is_american:
            j = np.arange(n + 1)
            spot_n = S * (u ** j) * (d ** (n - j))
            if is_call:
                intrinsic = np.maximum(spot_n - K, 0.0)
            else:
                intrinsic = np.maximum(K - spot_n, 0.0)
            V = np.maximum(cont, intrinsic)
        else:
            V = cont

    return float(V[0])


def price_binomial(inputs: OptionInputs, steps: int = 200) -> PricerResult:
    price = _binomial_tree_price(inputs, steps)

    def _p(inp: OptionInputs) -> float:
        return _binomial_tree_price(inp, steps)

    greeks = compute_greeks_fd(_p, inputs)
    return PricerResult(
        price=float(price),
        delta=greeks.delta,
        gamma=greeks.gamma,
        theta=greeks.theta,
        vega=greeks.vega,
        rho=greeks.rho,
    )


def price_binomial_european(inputs: OptionInputs, steps: int = 200) -> PricerResult:
    from dataclasses import replace

    eu = replace(inputs, style=ExerciseStyle.EUROPEAN)
    return price_binomial(eu, steps=steps)
