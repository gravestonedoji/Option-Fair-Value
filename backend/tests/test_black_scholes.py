from __future__ import annotations

import math

import pytest

from app.pricing import OptionInputs, OptionType, price_bs


def _atm_call(**kw):
    base = dict(spot=100.0, strike=100.0, time_to_expiry=1.0, risk_free_rate=0.05,
                volatility=0.20, dividend_yield=0.0, option_type=OptionType.CALL)
    base.update(kw)
    return OptionInputs(**base)


def test_bs_atm_call_price_and_greeks():
    r = price_bs(_atm_call())
    assert math.isclose(r.price, 10.4506, abs_tol=1e-3)
    assert math.isclose(r.delta, 0.6368, abs_tol=1e-3)
    assert math.isclose(r.gamma, 0.0188, abs_tol=1e-3)
    assert math.isclose(r.vega, 0.3752, abs_tol=1e-3)
    assert math.isclose(r.theta, -0.01758, abs_tol=1e-3)
    assert math.isclose(r.rho, 0.5323, abs_tol=1e-3)


def test_bs_atm_put_price_and_delta():
    r = price_bs(_atm_call(option_type=OptionType.PUT))
    assert math.isclose(r.price, 5.5735, abs_tol=1e-3)
    assert math.isclose(r.delta, -0.3632, abs_tol=1e-3)


def test_bs_with_dividend():
    r = price_bs(_atm_call(dividend_yield=0.02))
    assert r.price < 10.4506


def test_bs_t_zero_returns_intrinsic():
    r = price_bs(_atm_call(time_to_expiry=0.0))
    assert r.price == 0.0
    assert r.delta is None


def test_bs_t_zero_itm_call_intrinsic():
    r = price_bs(_atm_call(spot=120.0, time_to_expiry=0.0))
    assert math.isclose(r.price, 20.0, abs_tol=1e-12)


def test_bs_sigma_zero_returns_intrinsic():
    r = price_bs(_atm_call(volatility=0.0))
    assert r.price == 0.0
    assert r.delta is None


def test_bs_sigma_zero_itm_put_intrinsic():
    r = price_bs(_atm_call(spot=80.0, option_type=OptionType.PUT, volatility=0.0))
    assert math.isclose(r.price, 20.0, abs_tol=1e-12)


def test_bs_put_call_parity():
    call = price_bs(_atm_call(option_type=OptionType.CALL)).price
    put = price_bs(_atm_call(option_type=OptionType.PUT)).price
    S, K, r, T = 100.0, 100.0, 0.05, 1.0
    parity = call - put - S + K * math.exp(-r * T)
    assert math.isclose(parity, 0.0, abs_tol=1e-9)
