import math

import pytest

from app.pricing.black_scholes import OptionInputs, OptionType, price_bs
from app.pricing.implied_vol import (
    black76_price,
    black76_vega,
    implied_vol_black76,
)

_R = 0.05


def test_round_trip_grid():
    F = 100.0
    for sigma in (0.1, 0.3, 0.8):
        for k in (-0.3, -0.1, 0.0, 0.1, 0.3):
            K = F * math.exp(k)
            for T in (0.02, 0.25, 1.0):
                for opt in (OptionType.CALL, OptionType.PUT):
                    price = black76_price(F, K, T, _R, sigma, opt)
                    if opt is OptionType.CALL:
                        intrinsic = math.exp(-_R * T) * max(F - K, 0.0)
                    else:
                        intrinsic = math.exp(-_R * T) * max(K - F, 0.0)
                    res = implied_vol_black76(price, F, K, T, _R, opt)
                    if price - intrinsic < 1e-9:
                        # Time value at/below float precision: sigma is
                        # ill-conditioned. Solver may bail cleanly or solve;
                        # if it solves, it must at least reprice correctly.
                        assert res.status in ("ok", "below_intrinsic")
                        if res.status == "ok":
                            rebuilt = black76_price(F, K, T, _R, res.iv, opt)
                            assert math.isclose(rebuilt, price, abs_tol=1e-8)
                        continue
                    assert res.status == "ok", (sigma, k, T, opt, res.status)
                    assert math.isclose(res.iv, sigma, abs_tol=1e-6)


def test_black76_matches_bs_at_forward():
    S, K, T, r, sigma = 100.0, 95.0, 0.5, 0.05, 0.25
    F = S * math.exp(r * T)
    for opt in (OptionType.CALL, OptionType.PUT):
        b76 = black76_price(F, K, T, r, sigma, opt)
        bs = price_bs(
            OptionInputs(
                spot=S,
                strike=K,
                time_to_expiry=T,
                risk_free_rate=r,
                volatility=sigma,
                dividend_yield=0.0,
                option_type=opt,
            )
        ).price
        assert math.isclose(b76, bs, abs_tol=1e-9)


def test_below_intrinsic_status():
    F, K, T = 100.0, 60.0, 0.5
    intrinsic = math.exp(-_R * T) * (F - K)
    res = implied_vol_black76(intrinsic - 0.01, F, K, T, _R, OptionType.CALL)
    assert res.status == "below_intrinsic"
    assert res.iv is None


def test_above_max_status():
    F, K, T = 100.0, 100.0, 0.5
    max_call = math.exp(-_R * T) * F
    res = implied_vol_black76(max_call + 0.01, F, K, T, _R, OptionType.CALL)
    assert res.status == "above_max"
    assert res.iv is None


@pytest.mark.parametrize(
    "price,F,K,T",
    [
        (1.0, 100.0, 100.0, 0.0),
        (1.0, 0.0, 100.0, 0.5),
        (1.0, 100.0, 0.0, 0.5),
        (0.0, 100.0, 100.0, 0.5),
        (-1.0, 100.0, 100.0, 0.5),
    ],
)
def test_bad_inputs_status(price, F, K, T):
    res = implied_vol_black76(price, F, K, T, _R, OptionType.CALL)
    assert res.status == "bad_inputs"
    assert res.iv is None


def test_tiny_premium_deep_otm_no_exception():
    # Deep OTM with a sub-cent premium: must return a clean status, never raise.
    res = implied_vol_black76(0.0005, 100.0, 200.0, 0.02, _R, OptionType.CALL)
    assert res.status in ("ok", "no_convergence")
    if res.status == "ok":
        rebuilt = black76_price(100.0, 200.0, 0.02, _R, res.iv, OptionType.CALL)
        assert math.isclose(rebuilt, 0.0005, abs_tol=1e-8)


def test_vega_positive_and_consistent_at_solution():
    F, K, T, sigma = 100.0, 110.0, 0.5, 0.3
    price = black76_price(F, K, T, _R, sigma, OptionType.CALL)
    res = implied_vol_black76(price, F, K, T, _R, OptionType.CALL)
    assert res.status == "ok"
    assert res.vega is not None and res.vega > 0.0
    assert math.isclose(res.vega, black76_vega(F, K, T, _R, res.iv), abs_tol=1e-12)


def test_put_call_parity_black76():
    F, K, T, sigma = 100.0, 105.0, 0.75, 0.4
    call = black76_price(F, K, T, _R, sigma, OptionType.CALL)
    put = black76_price(F, K, T, _R, sigma, OptionType.PUT)
    assert math.isclose(call - put, math.exp(-_R * T) * (F - K), abs_tol=1e-9)
