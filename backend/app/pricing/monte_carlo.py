from __future__ import annotations

import math
from typing import Optional, Union, overload

import numpy as np

from app.pricing.black_scholes import ExerciseStyle, OptionInputs, OptionType, PricerResult, _intrinsic
from app.pricing.greeks import compute_greeks_fd


def _mc_price_only(
    inputs: OptionInputs, n_paths: int, seed: Optional[int], n_steps: int = 50
) -> tuple[float, np.ndarray]:
    S = float(inputs.spot)
    K = float(inputs.strike)
    T = float(inputs.time_to_expiry)
    r = float(inputs.risk_free_rate)
    q = float(inputs.dividend_yield)
    sigma = float(inputs.volatility)
    is_call = inputs.option_type is OptionType.CALL

    if T <= 0.0 or sigma <= 0.0 or S <= 0.0 or K <= 0.0:
        p = _intrinsic(inputs).price
        return p, np.array([p], dtype=float)

    rng = np.random.default_rng(seed)

    if inputs.style is ExerciseStyle.AMERICAN:
        return _price_american_ls(inputs, n_paths=n_paths, n_steps=n_steps, rng=rng)

    n_half = max(n_paths // 2, 1)
    Z = rng.standard_normal(n_half)
    Z_full = np.concatenate([Z, -Z])
    drift = (r - q - 0.5 * sigma * sigma) * T
    vol = sigma * math.sqrt(T)
    S_T = S * np.exp(drift + vol * Z_full)
    payoff = np.maximum(S_T - K, 0.0) if is_call else np.maximum(K - S_T, 0.0)
    discount = math.exp(-r * T)
    samples = payoff * discount
    return float(samples.mean()), samples


@overload
def price_monte_carlo(
    inputs: OptionInputs,
    n_paths: int = 50_000,
    seed: Optional[int] = None,
    return_samples: bool = False,
) -> PricerResult: ...


@overload
def price_monte_carlo(
    inputs: OptionInputs,
    n_paths: int = 50_000,
    seed: Optional[int] = None,
    return_samples: bool = True,
) -> tuple[PricerResult, np.ndarray]: ...


def price_monte_carlo(
    inputs: OptionInputs,
    n_paths: int = 50_000,
    seed: Optional[int] = None,
    return_samples: bool = False,
) -> Union[PricerResult, tuple[PricerResult, np.ndarray]]:
    price, samples = _mc_price_only(inputs, n_paths=n_paths, seed=seed)

    def _p(inp: OptionInputs) -> float:
        return _mc_price_only(inp, n_paths=n_paths, seed=seed)[0]

    greeks = compute_greeks_fd(_p, inputs)

    result = PricerResult(
        price=float(price),
        delta=greeks.delta,
        gamma=greeks.gamma,
        theta=greeks.theta,
        vega=greeks.vega,
        rho=greeks.rho,
    )

    if return_samples:
        return result, samples
    return result


def _mc_batch_prices(
    inputs_list: list[OptionInputs],
    n_paths: int,
    seed: Optional[int],
    n_steps: int = 50,
) -> np.ndarray:
    """Batched Monte Carlo pricing for multiple inputs in one vectorised pass.

    All inputs must share the same ``option_type`` and ``strike`` (only spot,
    volatility, rate, and time-to-expiry may vary).  Uses *common random
    numbers* — the same antithetic Z is shared across every input — which
    reduces variance when comparing prices across the LHS sweep.

    Returns
    -------
    np.ndarray
        Shape ``(n_batch,)`` array of option prices.
    """
    n_batch = len(inputs_list)
    if n_batch == 0:
        return np.empty(0, dtype=float)

    first = inputs_list[0]
    K = float(first.strike)
    is_call = first.option_type is OptionType.CALL
    style = first.style

    spots = np.array([float(inp.spot) for inp in inputs_list])
    sigmas = np.array([float(inp.volatility) for inp in inputs_list])
    rates = np.array([float(inp.risk_free_rate) for inp in inputs_list])
    Ts = np.array([float(inp.time_to_expiry) for inp in inputs_list])
    qs = np.array([float(inp.dividend_yield) for inp in inputs_list])

    prices = np.zeros(n_batch, dtype=float)

    degenerate = (Ts <= 0.0) | (sigmas <= 0.0) | (spots <= 0.0) | (K <= 0.0)
    if degenerate.any():
        for i in np.where(degenerate)[0]:
            prices[i] = _intrinsic(inputs_list[i]).price

    active = ~degenerate
    if not active.any():
        return prices

    spots_a = spots[active]
    sigmas_a = sigmas[active]
    rates_a = rates[active]
    Ts_a = Ts[active]
    qs_a = qs[active]
    n_active = active.sum()
    active_idx = np.where(active)[0]

    rng = np.random.default_rng(seed)
    n_half = max(n_paths // 2, 1)

    if style is ExerciseStyle.AMERICAN:
        active_prices = _batch_american_ls(
            spots_a, sigmas_a, rates_a, Ts_a, qs_a,
            K, is_call, n_half, n_steps, rng,
        )
    else:
        Z = rng.standard_normal(n_half)
        Z_full = np.concatenate([Z, -Z])
        n_total = 2 * n_half
        drift = (rates_a - qs_a - 0.5 * sigmas_a ** 2) * Ts_a
        vol = sigmas_a * np.sqrt(Ts_a)
        S_T = spots_a[:, None] * np.exp(drift[:, None] + vol[:, None] * Z_full[None, :])
        if is_call:
            payoff = np.maximum(S_T - K, 0.0)
        else:
            payoff = np.maximum(K - S_T, 0.0)
        discount = np.exp(-rates_a * Ts_a)
        active_prices = (payoff * discount[:, None]).mean(axis=1)

    prices[active_idx] = active_prices
    return prices


def _batch_american_ls(
    spots: np.ndarray,
    sigmas: np.ndarray,
    rates: np.ndarray,
    Ts: np.ndarray,
    qs: np.ndarray,
    K: float,
    is_call: bool,
    n_half: int,
    n_steps: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Vectorised American LSMC across many parameter sets at once.

    Parameters are 1-D arrays of shape ``(n_active,)``.  The same antithetic
    random walk is shared across all sets (common random numbers).
    """
    n_active = spots.shape[0]
    n_total = 2 * n_half

    dt = Ts / n_steps
    drift = (rates - qs - 0.5 * sigmas ** 2) * dt
    vol = sigmas * np.sqrt(dt)

    Z = rng.standard_normal((n_half, n_steps))
    Z_full = np.concatenate([Z, -Z], axis=0)

    increments = np.exp(
        drift[:, None, None] + vol[:, None, None] * Z_full[None, :, :]
    )
    del Z, Z_full

    path = np.empty((n_active, n_total, n_steps + 1), dtype=np.float64)
    path[:, :, 0] = spots[:, None]
    path[:, :, 1:] = spots[:, None, None] * np.cumprod(increments, axis=2)
    del increments

    ex_time = np.full((n_active, n_total), n_steps, dtype=np.int64)
    ex_val: np.ndarray
    if is_call:
        ex_val = np.maximum(path[:, :, n_steps] - K, 0.0).copy()
    else:
        ex_val = np.maximum(K - path[:, :, n_steps], 0.0).copy()

    dt_b = dt[:, None]
    rates_b = rates[:, None]

    for t in range(n_steps - 1, 0, -1):
        S_t = path[:, :, t]
        S2 = S_t * S_t
        if is_call:
            X = np.maximum(S_t - K, 0.0)
        else:
            X = np.maximum(K - S_t, 0.0)

        future_disc = np.exp(-rates_b * (ex_time - t) * dt_b)
        Y = ex_val * future_disc

        SY = S_t * Y
        S2Y = S2 * Y

        # Normal equations for Y ~ c0 + c1*S + c2*S^2:
        #   [n   ΣS   ΣS2 ] [c0]   [ΣY  ]
        #   [ΣS  ΣS2  ΣS3 ] [c1] = [ΣSY ]
        #   [ΣS2 ΣS3  ΣS4 ] [c2]   [ΣS2Y]
        n = n_total
        sumS = S_t.sum(axis=1)
        sumS2 = S2.sum(axis=1)
        sumS3 = (S2 * S_t).sum(axis=1)
        sumS4 = (S2 * S2).sum(axis=1)
        sumY = Y.sum(axis=1)
        sumSY = SY.sum(axis=1)
        sumS2Y = S2Y.sum(axis=1)

        AtA = np.stack([
            np.stack([np.full(n_active, n), sumS, sumS2], axis=-1),
            np.stack([sumS, sumS2, sumS3], axis=-1),
            np.stack([sumS2, sumS3, sumS4], axis=-1),
        ], axis=-2)  # (n_active, 3, 3)
        AtY = np.stack([sumY, sumSY, sumS2Y], axis=-1)  # (n_active, 3)
        coeffs = np.linalg.solve(AtA, AtY[:, :, None])[:, :, 0]  # (n_active, 3)

        cont_est = coeffs[:, 0:1] + coeffs[:, 1:2] * S_t + coeffs[:, 2:3] * S2

        exercise_now = X > cont_est
        if exercise_now.any():
            ex_time = np.where(exercise_now, t, ex_time)
            ex_val = np.where(exercise_now, X, ex_val)

    pv = ex_val * np.exp(-rates_b * ex_time * dt_b)
    return pv.mean(axis=1)


def _price_american_ls(
    inputs: OptionInputs, n_paths: int, n_steps: int, rng: np.random.Generator
) -> tuple[float, np.ndarray]:
    S = float(inputs.spot)
    K = float(inputs.strike)
    T = float(inputs.time_to_expiry)
    r = float(inputs.risk_free_rate)
    q = float(inputs.dividend_yield)
    sigma = float(inputs.volatility)
    is_call = inputs.option_type is OptionType.CALL

    dt = T / n_steps
    drift = (r - q - 0.5 * sigma * sigma) * dt
    vol = sigma * math.sqrt(dt)

    n_half = max(n_paths // 2, 1)
    Z = rng.standard_normal((n_half, n_steps))
    Z_full = np.vstack([Z, -Z])
    increments = np.exp(drift + vol * Z_full)

    n_total = 2 * n_half
    path = np.empty((n_total, n_steps + 1), dtype=float)
    path[:, 0] = S
    for t in range(1, n_steps + 1):
        path[:, t] = path[:, t - 1] * increments[:, t - 1]

    if is_call:
        payoff_fn = lambda x: np.maximum(x - K, 0.0)
    else:
        payoff_fn = lambda x: np.maximum(K - x, 0.0)

    exercise_value = payoff_fn(path)
    exercise_time = np.full(n_total, n_steps, dtype=int)
    exercise_value_at_t = exercise_value[:, n_steps].copy()

    for t in range(n_steps - 1, 0, -1):
        itm = exercise_value[:, t] > 0.0
        if not np.any(itm):
            continue
        S_t = path[itm, t]
        X = exercise_value[itm, t]
        future_disc = np.exp(-r * (exercise_time[itm] - t) * dt)
        Y = exercise_value_at_t[itm] * future_disc
        A = np.column_stack([np.ones_like(S_t), S_t, S_t * S_t])
        coeffs, _, _, _ = np.linalg.lstsq(A, Y, rcond=None)
        cont_est = A @ coeffs
        exercise_now = X > cont_est
        if np.any(exercise_now):
            global_idx = np.where(itm)[0][exercise_now]
            exercise_time[global_idx] = t
            exercise_value_at_t[global_idx] = X[exercise_now]

    pv_per_path = exercise_value_at_t * np.exp(-r * exercise_time * dt)
    return float(pv_per_path.mean()), pv_per_path
