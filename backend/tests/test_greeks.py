from __future__ import annotations

import math

from app.pricing import OptionInputs, OptionType, compute_greeks_fd, price_bs


def _atm(**kw):
    base = dict(spot=100.0, strike=100.0, time_to_expiry=1.0, risk_free_rate=0.05,
                volatility=0.20, dividend_yield=0.0, option_type=OptionType.CALL)
    base.update(kw)
    return OptionInputs(**base)


def test_fd_greeks_match_analytic_bs_call():
    analytic = price_bs(_atm())
    fd = compute_greeks_fd(lambda inp: price_bs(inp).price, _atm())
    assert math.isclose(fd.delta, analytic.delta, rel_tol=0.01)
    assert math.isclose(fd.gamma, analytic.gamma, rel_tol=0.01)
    assert math.isclose(fd.vega, analytic.vega, rel_tol=0.01)
    assert math.isclose(fd.rho, analytic.rho, rel_tol=0.01)
    assert math.isclose(fd.theta, analytic.theta, rel_tol=0.01)


def test_fd_greeks_match_analytic_bs_put():
    analytic = price_bs(_atm(option_type=OptionType.PUT))
    fd = compute_greeks_fd(lambda inp: price_bs(inp).price, _atm(option_type=OptionType.PUT))
    assert math.isclose(fd.delta, analytic.delta, rel_tol=0.01)
    assert math.isclose(fd.gamma, analytic.gamma, rel_tol=0.01)
    assert math.isclose(fd.vega, analytic.vega, rel_tol=0.01)
    assert math.isclose(fd.rho, analytic.rho, rel_tol=0.01)
    assert math.isclose(fd.theta, analytic.theta, rel_tol=0.01)


def test_fd_greeks_price_equals_pricer():
    fd = compute_greeks_fd(lambda inp: price_bs(inp).price, _atm())
    assert math.isclose(fd.price, price_bs(_atm()).price, abs_tol=1e-12)


def test_fd_greeks_on_simple_lambda():
    def linear_pricer(inp: OptionInputs) -> float:
        return inp.spot - inp.strike

    fd = compute_greeks_fd(linear_pricer, _atm())
    assert math.isclose(fd.delta, 1.0, rel_tol=1e-6)
    assert math.isclose(fd.gamma, 0.0, abs_tol=1e-6)
