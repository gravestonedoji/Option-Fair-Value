import math
from datetime import date, timedelta

import pytest

from app.analysis import AnalysisParams, analyze_chain, fit_smile, infer_forward
from app.data.models import OptionChain, OptionChainRow, OptionQuote
from app.pricing.black_scholes import OptionType
from app.pricing.implied_vol import black76_price

_ASOF = date(2026, 1, 15)
_RATE = 0.04
_SMILE = (0.25, -0.15, 0.4)  # sigma(k) = a + b*k + c*k^2


def _smile_iv(k: float, smile=_SMILE) -> float:
    a, b, c = smile
    return a + b * k + c * k * k


def _quote(strike: float, mid: float, half_spread_pct: float, oi: int, volume: int) -> OptionQuote:
    return OptionQuote(
        strike=strike,
        bid=mid * (1.0 - half_spread_pct),
        ask=mid * (1.0 + half_spread_pct),
        mid=mid,
        iv=None,
        open_interest=oi,
        volume=volume,
        in_the_money=None,
    )


def _requote(row: OptionChainRow, side: str, mid: float, half_spread_pct: float = 0.02) -> None:
    quote = getattr(row, side)
    quote.mid = mid
    quote.bid = mid * (1.0 - half_spread_pct)
    quote.ask = mid * (1.0 + half_spread_pct)


def make_synthetic_chain(
    spot: float = 100.0,
    strikes=None,
    smile=_SMILE,
    rate: float = _RATE,
    dte_days: int = 30,
    asof: date = _ASOF,
    half_spread_pct: float = 0.02,
    oi: int = 100,
    volume: int = 50,
) -> OptionChain:
    """Chain whose mids are exact Black-76 prices off sigma(k) = a + b*k + c*k^2.

    European parity holds by construction, so the parity-implied forward is
    exactly spot * e^{rT}.
    """
    if strikes is None:
        strikes = [70.0 + 2.5 * i for i in range(25)]  # 70 .. 130
    T = dte_days / 365.0
    forward = spot * math.exp(rate * T)

    rows = []
    for K in strikes:
        k = math.log(K / forward)
        sigma = _smile_iv(k, smile)
        call_mid = black76_price(forward, K, T, rate, sigma, OptionType.CALL)
        put_mid = black76_price(forward, K, T, rate, sigma, OptionType.PUT)
        rows.append(
            OptionChainRow(
                strike=K,
                call=_quote(K, call_mid, half_spread_pct, oi, volume),
                put=_quote(K, put_mid, half_spread_pct, oi, volume),
            )
        )
    return OptionChain.build(symbol="SYN", expiry=asof + timedelta(days=dte_days), spot=spot, rows=rows)


def _contract(analysis, opt_type: str, strike: float):
    for c in analysis.contracts:
        if c.type == opt_type and math.isclose(c.strike, strike):
            return c
    raise AssertionError(f"contract {opt_type} {strike} not found")


def _analyze(chain, params=None):
    return analyze_chain(chain, _RATE, "fallback", params=params, asof=_ASOF)


# --- forward inference -------------------------------------------------------


def test_forward_recovery_from_parity():
    chain = make_synthetic_chain()
    T = 30 / 365.0
    forward, source, n_pairs, parity = infer_forward(chain, _RATE, T, AnalysisParams())
    assert source == "parity"
    assert n_pairs == AnalysisParams().near_atm_pairs
    assert math.isclose(forward, 100.0 * math.exp(_RATE * T), rel_tol=1e-9)
    assert len(parity) == len(chain.rows)
    assert not any(rec.check_flag for rec in parity)


def test_forward_fallback_without_puts():
    chain = make_synthetic_chain()
    for row in chain.rows:
        row.put.mid = None
        row.put.bid = None
        row.put.ask = None
    T = 30 / 365.0
    forward, source, n_pairs, parity = infer_forward(chain, _RATE, T, AnalysisParams())
    assert source == "spot_carry_fallback"
    assert n_pairs == 0
    assert math.isclose(forward, 100.0 * math.exp(_RATE * T), rel_tol=1e-12)
    assert parity == []


def test_forward_ignores_zero_bid_and_crossed_pairs():
    chain = make_synthetic_chain()
    # Corrupt six near-ATM put mids: garbage prices that WOULD move the median
    # if included, marked untrustworthy via zero bids / crossed quotes. Six
    # because a median over 11 pairs absorbs up to 5 outliers.
    for K in (95.0, 97.5, 100.0):
        q = next(r for r in chain.rows if r.strike == K).put
        q.mid += 5.0
        q.bid = 0.0
    for K in (102.5, 105.0, 107.5):
        q = next(r for r in chain.rows if r.strike == K).put
        q.mid += 5.0
        q.bid = q.mid * 1.02
        q.ask = q.mid * 0.98  # crossed
    T = 30 / 365.0
    forward, source, n_pairs, _ = infer_forward(chain, _RATE, T, AnalysisParams())
    assert source == "parity"
    assert n_pairs == AnalysisParams().near_atm_pairs
    assert math.isclose(forward, 100.0 * math.exp(_RATE * T), rel_tol=1e-9)


def test_forward_sanity_clamp_falls_back_to_spot_carry():
    chain = make_synthetic_chain()
    # Every in-band pair implies F ~ 400, outside [0.5, 2.0] x spot.
    for row in chain.rows:
        if 80.0 <= row.strike <= 120.0:
            _requote(row, "call", row.call.mid + 300.0)
    T = 30 / 365.0
    forward, source, n_pairs, _ = infer_forward(chain, _RATE, T, AnalysisParams())
    assert source == "spot_carry_fallback"
    assert n_pairs == AnalysisParams().near_atm_pairs  # pairs existed, F was junk
    assert math.isclose(forward, 100.0 * math.exp(_RATE * T), rel_tol=1e-12)


# --- clean chain: fit recovery, no false flags -------------------------------


def test_clean_chain_recovers_smile_and_flags_nothing():
    analysis = _analyze(make_synthetic_chain())
    assert analysis.forward_source == "parity"
    fit = analysis.fit
    assert fit.fitted and fit.degree == 2
    a, b, c = _SMILE
    # numpy polyfit order: highest power first
    assert math.isclose(fit.coefficients[0], c, abs_tol=1e-5)
    assert math.isclose(fit.coefficients[1], b, abs_tol=1e-5)
    assert math.isclose(fit.coefficients[2], a, abs_tol=1e-6)
    assert fit.rmse < 1e-6
    # MAD floor keeps numerical noise from being flagged
    assert math.isclose(fit.sigma_mad, AnalysisParams().mad_floor)
    assert analysis.flagged_count == 0
    assert all(c.verdict is None for c in analysis.contracts)


def test_otm_model_contracts_used_in_fit():
    analysis = _analyze(make_synthetic_chain())
    for c in analysis.contracts:
        if c.is_otm and c.iv_source == "model" and "far_otm" not in c.filters_failed:
            assert c.used_in_fit
        if not c.is_otm:
            assert not c.used_in_fit
            assert "itm" in c.filters_failed


# --- flagging ----------------------------------------------------------------


def test_perturbed_contract_flagged_rich():
    chain = make_synthetic_chain()
    K = 115.0
    T = 30 / 365.0
    forward = 100.0 * math.exp(_RATE * T)
    k = math.log(K / forward)
    bumped = black76_price(forward, K, T, _RATE, _smile_iv(k) + 0.04, OptionType.CALL)
    row = next(r for r in chain.rows if r.strike == K)
    _requote(row, "call", bumped)

    analysis = _analyze(chain)
    flagged = [c for c in analysis.contracts if c.verdict is not None]
    assert len(flagged) == 1 and analysis.flagged_count == 1
    c = flagged[0]
    assert (c.type, c.strike, c.verdict) == ("call", K, "rich")
    assert c.z is not None and c.z >= AnalysisParams().z_threshold
    assert math.isclose(c.iv, _smile_iv(k) + 0.04, abs_tol=1e-4)


def test_perturbed_contract_flagged_cheap():
    chain = make_synthetic_chain()
    K = 85.0  # OTM put
    T = 30 / 365.0
    forward = 100.0 * math.exp(_RATE * T)
    k = math.log(K / forward)
    dropped = black76_price(forward, K, T, _RATE, _smile_iv(k) - 0.04, OptionType.PUT)
    row = next(r for r in chain.rows if r.strike == K)
    _requote(row, "put", dropped)

    analysis = _analyze(chain)
    flagged = [c for c in analysis.contracts if c.verdict is not None]
    assert len(flagged) == 1
    assert (flagged[0].type, flagged[0].strike, flagged[0].verdict) == ("put", K, "cheap")


def test_illiquid_outlier_reported_but_not_flagged():
    chain = make_synthetic_chain()
    K = 115.0
    T = 30 / 365.0
    forward = 100.0 * math.exp(_RATE * T)
    k = math.log(K / forward)
    bumped = black76_price(forward, K, T, _RATE, _smile_iv(k) + 0.04, OptionType.CALL)
    row = next(r for r in chain.rows if r.strike == K)
    _requote(row, "call", bumped)
    row.call.open_interest = 0
    row.call.volume = 0

    analysis = _analyze(chain)
    c = _contract(analysis, "call", K)
    assert c.verdict is None
    assert "low_liquidity" in c.filters_failed
    assert c.z is not None and abs(c.z) >= AnalysisParams().z_threshold
    assert analysis.flagged_count == 0


def test_inside_spread_suppresses_flag():
    # Near-ATM so vega is high: a z>threshold IV bump moves the price less
    # than a widened-but-still-liquid half-spread, so the materiality gate
    # must suppress the verdict.
    chain = make_synthetic_chain()
    K = 100.0  # OTM put (K < forward)
    T = 30 / 365.0
    forward = 100.0 * math.exp(_RATE * T)
    k = math.log(K / forward)
    bumped = black76_price(forward, K, T, _RATE, _smile_iv(k) + 0.014, OptionType.PUT)
    row = next(r for r in chain.rows if r.strike == K)
    _requote(row, "put", bumped, half_spread_pct=0.065)  # rel spread 13% < 25%

    analysis = _analyze(chain)
    c = _contract(analysis, "put", K)
    assert c.z is not None and abs(c.z) >= AnalysisParams().z_threshold
    assert abs(c.price_edge) <= (c.ask - c.bid) / 2.0
    assert "wide_spread" not in c.filters_failed
    assert "inside_spread" in c.filters_failed
    assert c.verdict is None
    assert analysis.flagged_count == 0


def test_wide_spread_excluded_from_fit_and_flags():
    chain = make_synthetic_chain()
    K = 110.0
    row = next(r for r in chain.rows if r.strike == K)
    _requote(row, "call", row.call.mid, half_spread_pct=0.30)  # rel spread 60%

    analysis = _analyze(chain)
    c = _contract(analysis, "call", K)
    assert not c.used_in_fit
    assert "wide_spread" in c.filters_failed
    assert c.verdict is None


def test_sparse_chain_degrades_to_unfitted():
    chain = make_synthetic_chain(strikes=[95.0, 100.0, 105.0])
    analysis = _analyze(chain)
    assert not analysis.fit.fitted
    assert analysis.fit.reason == "insufficient_points"
    assert analysis.flagged_count == 0
    assert all(c.verdict is None and c.fitted_iv is None for c in analysis.contracts)
    # IVs are still solved and reported even without a fit
    assert any(c.iv_source == "model" for c in analysis.contracts)


def test_narrow_k_span_demotes_to_linear_and_flags_nothing():
    # Tight strikes around the forward (~100.33): usable k-span ~0.012,
    # inside the [0.005, 0.02) degree-demotion window.
    chain = make_synthetic_chain(
        strikes=[99.8, 100.0, 100.2, 100.4, 100.6, 100.8, 101.0]
    )
    analysis = _analyze(chain)
    fit = analysis.fit
    assert fit.fitted
    span = fit.k_max - fit.k_min
    assert 0.005 <= span < 0.02, "fixture must land in the demotion window"
    assert fit.degree == 1
    assert len(fit.coefficients) == 2
    assert analysis.flagged_count == 0
    assert all(c.verdict is None for c in analysis.contracts)


def test_clustered_strikes_degrade_to_degenerate_k_range():
    # Enough points (>= min_fit_points) but log-moneyness span 0.004 < 0.005.
    points = [(k, _smile_iv(k), 1.0) for k in (0.0, 0.001, 0.002, 0.003, 0.004)]
    fit = fit_smile(points, AnalysisParams())
    assert not fit.fitted
    assert fit.reason == "degenerate_k_range"
    assert fit.coefficients == []


def test_band_unavailable_with_two_clean_contracts_degrades_unbanded():
    # Only 2 clean OTM quotes survive the fit filters, so _fit_band has fewer
    # than 3 anchor IVs: no far_otm banding is applied and the fit degrades to
    # insufficient_points without crashing.
    chain = make_synthetic_chain()
    keep = {("put", 97.5), ("call", 105.0)}
    for row in chain.rows:
        for side in ("call", "put"):
            if (side, row.strike) in keep:
                continue
            q = getattr(row, side)
            if q.mid is not None:
                q.bid = q.mid * 0.5
                q.ask = q.mid * 1.5  # rel spread 100% > max_rel_spread

    analysis = _analyze(chain)
    used = {(c.type, c.strike) for c in analysis.contracts if c.used_in_fit}
    assert used == keep
    assert not any("far_otm" in c.filters_failed for c in analysis.contracts)
    assert not analysis.fit.fitted
    assert analysis.fit.reason == "insufficient_points"
    assert analysis.flagged_count == 0
    # Per-contract IVs are still solved and reported in the degraded path.
    assert any(c.iv_source == "model" for c in analysis.contracts)


def test_otm_unsolvable_mid_with_yf_fallback_excluded_from_fit():
    chain = make_synthetic_chain()
    K = 110.0  # OTM call inside the fit band
    T = 30 / 365.0
    forward = 100.0 * math.exp(_RATE * T)
    row = next(r for r in chain.rows if r.strike == K)
    # Mid above the no-arb upper bound (discount * F): clean two-sided quote,
    # but no solvable Black-76 IV — the stale Yahoo IV must stay display-only.
    _requote(row, "call", math.exp(-_RATE * T) * forward + 1.0)
    row.call.iv = 0.30

    analysis = _analyze(chain)
    c = _contract(analysis, "call", K)
    assert c.is_otm
    assert c.iv_status == "above_max"
    assert c.iv_source == "yfinance"
    assert not c.used_in_fit
    assert "iv_unsolved" in c.filters_failed
    assert c.z is None and c.verdict is None
    # The Yahoo IV must not enter the fit: same fitted domain as the clean
    # chain, with exactly this one contract missing from the inputs.
    clean_fit = _analyze(make_synthetic_chain()).fit
    assert analysis.fit.n_used == clean_fit.n_used - 1
    assert analysis.fit.k_min == clean_fit.k_min
    assert analysis.fit.k_max == clean_fit.k_max


def test_below_intrinsic_mid_excluded_with_yf_fallback():
    chain = make_synthetic_chain()
    row = next(r for r in chain.rows if r.strike == 70.0)  # deep ITM call
    T = 30 / 365.0
    forward = 100.0 * math.exp(_RATE * T)
    intrinsic = math.exp(-_RATE * T) * (forward - 70.0)
    _requote(row, "call", intrinsic - 0.5)
    row.call.iv = 0.31  # stale yfinance IV survives as display-only fallback

    analysis = _analyze(chain)
    c = _contract(analysis, "call", 70.0)
    assert c.iv_status == "below_intrinsic"
    assert c.iv_source == "yfinance"
    assert math.isclose(c.iv, 0.31)
    assert not c.used_in_fit
    assert "iv_unsolved" in c.filters_failed
    assert c.verdict is None


def test_zero_bid_and_crossed_quotes_excluded():
    chain = make_synthetic_chain()
    row_a = next(r for r in chain.rows if r.strike == 120.0)
    row_a.call.bid = 0.0
    row_b = next(r for r in chain.rows if r.strike == 117.5)
    row_b.call.bid, row_b.call.ask = row_b.call.ask, row_b.call.bid  # crossed

    analysis = _analyze(chain)
    a = _contract(analysis, "call", 120.0)
    assert "no_bid" in a.filters_failed and not a.used_in_fit
    b = _contract(analysis, "call", 117.5)
    assert "crossed" in b.filters_failed and not b.used_in_fit


def test_itm_contract_never_flagged():
    chain = make_synthetic_chain()
    K = 85.0  # ITM call
    T = 30 / 365.0
    forward = 100.0 * math.exp(_RATE * T)
    k = math.log(K / forward)
    bumped = black76_price(forward, K, T, _RATE, _smile_iv(k) + 0.10, OptionType.CALL)
    row = next(r for r in chain.rows if r.strike == K)
    _requote(row, "call", bumped)

    analysis = _analyze(chain)
    c = _contract(analysis, "call", K)
    assert not c.is_otm
    assert not c.used_in_fit
    assert c.verdict is None
    assert "itm" in c.filters_failed


def test_one_day_to_expiry_ok_and_expired_raises():
    chain = make_synthetic_chain(dte_days=1)
    analysis = _analyze(chain)
    assert analysis.time_to_expiry == pytest.approx(1 / 365.0)

    expired = make_synthetic_chain(dte_days=0)
    with pytest.raises(ValueError):
        _analyze(expired)


def test_invalid_spot_rejected():
    for bad_spot in (0.0, float("nan")):
        chain = make_synthetic_chain().model_copy(update={"spot": bad_spot})
        with pytest.raises(ValueError, match="invalid spot"):
            _analyze(chain)


def test_parity_check_flag_on_broken_strike():
    chain = make_synthetic_chain()
    K = 120.0
    row = next(r for r in chain.rows if r.strike == K)
    _requote(row, "call", row.call.mid + 1.5)  # way outside combined spreads

    analysis = _analyze(chain)
    flagged = [rec for rec in analysis.parity if rec.check_flag]
    assert [rec.strike for rec in flagged] == [K]


def test_robust_refit_drops_outlier_and_recovers_smile():
    chain = make_synthetic_chain()
    K = 115.0
    T = 30 / 365.0
    forward = 100.0 * math.exp(_RATE * T)
    k = math.log(K / forward)
    bumped = black76_price(forward, K, T, _RATE, _smile_iv(k) + 0.04, OptionType.CALL)
    _requote(next(r for r in chain.rows if r.strike == K), "call", bumped)

    analysis = _analyze(chain)
    fit = analysis.fit
    # The outlier pulls the initial fit, so a couple of clean neighbors can
    # exceed the cutoff too on a noise-free chain; what matters is that the
    # refit recovers the true smile.
    assert fit.n_dropped >= 1
    assert fit.n_used >= 15
    a, b, c = _SMILE
    assert math.isclose(fit.coefficients[0], c, abs_tol=1e-4)
    assert math.isclose(fit.coefficients[1], b, abs_tol=1e-4)
    assert math.isclose(fit.coefficients[2], a, abs_tol=1e-5)


def test_far_otm_wings_excluded_from_fit_and_flags():
    chain = make_synthetic_chain()
    analysis = _analyze(chain)
    T = 30 / 365.0
    # ATM sigma is ~0.25, so the band is ~4 * 0.25 * sqrt(T) ~ 0.287; the
    # 70/72.5/75 puts (k < -0.29) sit outside it.
    wings = [
        c
        for c in analysis.contracts
        if abs(c.log_moneyness) > 4 * 0.26 * math.sqrt(T)
    ]
    assert wings, "test chain should reach beyond the fit band"
    for c in wings:
        assert "far_otm" in c.filters_failed
        assert not c.used_in_fit
        assert c.verdict is None
    # No extrapolation: nothing outside the fitted strike range gets a z.
    fit = analysis.fit
    for c in analysis.contracts:
        if not (fit.k_min <= c.log_moneyness <= fit.k_max):
            assert c.z is None and c.fitted_iv is None


def test_wing_outlier_not_flagged_against_extrapolation():
    # A perturbed quote in the far wing must NOT be flagged: the fit says
    # nothing about fair IV out there.
    chain = make_synthetic_chain()
    K = 70.0  # deepest OTM put, k ~ -0.36, outside the ~0.287 band
    T = 30 / 365.0
    forward = 100.0 * math.exp(_RATE * T)
    k = math.log(K / forward)
    bumped = black76_price(forward, K, T, _RATE, _smile_iv(k) + 0.10, OptionType.PUT)
    _requote(next(r for r in chain.rows if r.strike == K), "put", bumped)

    analysis = _analyze(chain)
    c = _contract(analysis, "put", K)
    assert c.verdict is None
    assert "far_otm" in c.filters_failed
    assert analysis.flagged_count == 0


def test_determinism():
    chain = make_synthetic_chain()
    a = _analyze(chain).model_dump(exclude={"computed_at"})
    b = _analyze(chain).model_dump(exclude={"computed_at"})
    assert a == b
