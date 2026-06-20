from __future__ import annotations

import math

from app.pricing import ExerciseStyle, OptionInputs, OptionType, price_binomial, price_bs


def _atm(**kw):
    base = dict(spot=100.0, strike=100.0, time_to_expiry=1.0, risk_free_rate=0.05,
                volatility=0.20, dividend_yield=0.0, option_type=OptionType.CALL,
                style=ExerciseStyle.EUROPEAN)
    base.update(kw)
    return OptionInputs(**base)


def test_binomial_european_converges_to_bs():
    bs = price_bs(_atm()).price
    bin_eu = price_binomial(_atm(), steps=200).price
    assert math.isclose(bin_eu, bs, abs_tol=0.05)


def test_binomial_european_put_converges_to_bs():
    bs = price_bs(_atm(option_type=OptionType.PUT)).price
    bin_eu = price_binomial(_atm(option_type=OptionType.PUT), steps=200).price
    assert math.isclose(bin_eu, bs, abs_tol=0.05)


def test_american_put_no_div_above_european():
    eu_put = price_binomial(_atm(option_type=OptionType.PUT), steps=200).price
    am_put = price_binomial(_atm(option_type=OptionType.PUT, style=ExerciseStyle.AMERICAN), steps=200).price
    assert am_put > eu_put


def test_american_call_no_div_equals_european():
    eu_call = price_binomial(_atm(), steps=200).price
    am_call = price_binomial(_atm(style=ExerciseStyle.AMERICAN), steps=200).price
    assert math.isclose(am_call, eu_call, abs_tol=1e-6)


def test_binomial_more_steps_converges():
    p50 = price_binomial(_atm(), steps=50).price
    p400 = price_binomial(_atm(), steps=400).price
    bs = price_bs(_atm()).price
    assert abs(p400 - bs) < abs(p50 - bs)


def test_binomial_greeks_present():
    r = price_binomial(_atm(), steps=200)
    assert r.delta is not None
    assert r.gamma is not None
    assert r.vega is not None
    assert math.isclose(r.delta, 0.6368, abs_tol=0.05)
