from __future__ import annotations

import math

import numpy as np

from app.pricing import ExerciseStyle, OptionInputs, OptionType, price_bs, price_monte_carlo


def _atm(**kw):
    base = dict(spot=100.0, strike=100.0, time_to_expiry=1.0, risk_free_rate=0.05,
                volatility=0.20, dividend_yield=0.0, option_type=OptionType.CALL,
                style=ExerciseStyle.EUROPEAN)
    base.update(kw)
    return OptionInputs(**base)


def test_mc_european_call_within_2pct_of_bs():
    bs = price_bs(_atm()).price
    mc = price_monte_carlo(_atm(), n_paths=50_000, seed=42).price
    assert abs(mc - bs) / bs < 0.02


def test_mc_european_put_within_2pct_of_bs():
    bs = price_bs(_atm(option_type=OptionType.PUT)).price
    mc = price_monte_carlo(_atm(option_type=OptionType.PUT), n_paths=50_000, seed=42).price
    assert abs(mc - bs) / bs < 0.02


def test_mc_reproducibility_same_seed():
    a = price_monte_carlo(_atm(), n_paths=20_000, seed=7).price
    b = price_monte_carlo(_atm(), n_paths=20_000, seed=7).price
    assert math.isclose(a, b, abs_tol=1e-12)


def test_mc_reproducibility_different_seed_diverges():
    a = price_monte_carlo(_atm(), n_paths=2_000, seed=1).price
    b = price_monte_carlo(_atm(), n_paths=2_000, seed=2).price
    assert not math.isclose(a, b, abs_tol=1e-9)


def test_mc_return_samples_shape():
    res, samples = price_monte_carlo(_atm(), n_paths=1_000, seed=3, return_samples=True)
    assert isinstance(samples, np.ndarray)
    assert samples.shape == (1_000,)
    assert math.isclose(samples.mean(), res.price, abs_tol=1e-9)


def test_mc_american_put_above_european_mc():
    eu = price_monte_carlo(_atm(option_type=OptionType.PUT), n_paths=20_000, seed=11).price
    am = price_monte_carlo(_atm(option_type=OptionType.PUT, style=ExerciseStyle.AMERICAN), n_paths=20_000, seed=11).price
    assert am >= eu - 1e-3


def test_mc_atm_puts_price_reasonable():
    bs = price_bs(_atm(option_type=OptionType.PUT, style=ExerciseStyle.AMERICAN)).price
    am = price_monte_carlo(_atm(option_type=OptionType.PUT, style=ExerciseStyle.AMERICAN), n_paths=50_000, seed=5).price
    assert abs(am - bs) / bs < 0.10
