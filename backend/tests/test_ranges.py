from __future__ import annotations

import math

import numpy as np

from app.pricing import (
    FairValueRange,
    InputBands,
    OptionInputs,
    OptionType,
    compute_fair_value_range,
    price_binomial,
    price_bs,
    price_monte_carlo,
)


def _atm(**kw):
    base = dict(spot=100.0, strike=100.0, time_to_expiry=30/365, risk_free_rate=0.05,
                volatility=0.20, dividend_yield=0.0, option_type=OptionType.CALL)
    base.update(kw)
    return OptionInputs(**base)


def test_range_returns_three_models():
    r = compute_fair_value_range(_atm(), InputBands(), n_lhs=30, mc_paths=2_000, seed=42)
    assert set(r.models.keys()) == {"black_scholes", "binomial", "monte_carlo"}


def test_range_ordering():
    r = compute_fair_value_range(_atm(), InputBands(), n_lhs=50, mc_paths=2_000, seed=42)
    for name, mr in r.models.items():
        assert mr.min <= mr.p5 <= mr.median <= mr.p95 <= mr.max, name


def test_range_base_equals_price_at_base_inputs():
    r = compute_fair_value_range(_atm(), InputBands(), n_lhs=20, mc_paths=2_000, seed=42)
    assert math.isclose(r.models["black_scholes"].base, price_bs(_atm()).price, abs_tol=1e-9)
    assert math.isclose(r.models["binomial"].base, price_binomial(_atm(), steps=200).price, abs_tol=1e-9)
    assert math.isclose(r.models["monte_carlo"].base, price_monte_carlo(_atm(), n_paths=2_000, seed=42).price, abs_tol=1e-9)


def test_range_deterministic_with_seed():
    a = compute_fair_value_range(_atm(), InputBands(), n_lhs=20, mc_paths=2_000, seed=42)
    b = compute_fair_value_range(_atm(), InputBands(), n_lhs=20, mc_paths=2_000, seed=42)
    for name in a.models:
        assert math.isclose(a.models[name].median, b.models[name].median, abs_tol=1e-12)


def test_range_samples_dict_has_per_lhs_arrays():
    r = compute_fair_value_range(_atm(), InputBands(), n_lhs=25, mc_paths=1_000, seed=1)
    for name in r.samples:
        assert r.samples[name].shape == (25,)


def test_range_base_results_present():
    r = compute_fair_value_range(_atm(), InputBands(), n_lhs=10, mc_paths=1_000, seed=1)
    assert set(r.base_results.keys()) == {"black_scholes", "binomial", "monte_carlo"}


def test_range_wider_bands_wider_output():
    narrow = compute_fair_value_range(_atm(), InputBands(vol_pct=0.05, spot_pct=0.01, rate_bps=10, dte_days=0.5), n_lhs=20, mc_paths=1_000, seed=1)
    wide = compute_fair_value_range(_atm(), InputBands(vol_pct=0.40, spot_pct=0.10, rate_bps=100, dte_days=5.0), n_lhs=20, mc_paths=1_000, seed=1)
    assert wide.models["black_scholes"].max > narrow.models["black_scholes"].max
    assert wide.models["black_scholes"].min < narrow.models["black_scholes"].min
