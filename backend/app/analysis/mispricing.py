"""IV relative-value analysis of an option chain.

Pure functions, no I/O. The pipeline per expiry:

1. Infer the implied forward from put-call parity over near-ATM pairs
   (absorbs dividends without needing a dividend-yield estimate).
2. Solve our own Black-76 IVs from OTM mids; Yahoo's IV column is kept as a
   display-only fallback and never enters the fit.
3. Robust vega-weighted polynomial fit of IV on log-moneyness.
4. Flag contracts whose IV sits far off the fitted smile (robust z-score),
   gated by liquidity filters and a price-materiality check (fitted price
   must fall outside the quoted bid-ask).

Flags are relative-value screening signals on delayed data — never arbitrage.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from statistics import median
from typing import Optional

import numpy as np

from app.data.models import OptionChain, OptionQuote
from app.pricing.black_scholes import OptionType
from app.pricing.implied_vol import black76_price, implied_vol_black76

from .models import (
    AnalysisParams,
    ChainAnalysis,
    ContractAnalysis,
    ParityRecord,
    SmileFitInfo,
)

# Strikes further than this from spot are excluded from forward inference
# (wide-moneyness pairs carry the most early-exercise/staleness noise).
_PARITY_MONEYNESS_BAND = 0.20
# Inferred forward outside [0.5, 2.0] x spot means the parity data is junk.
_FORWARD_SANITY_LO = 0.5
_FORWARD_SANITY_HI = 2.0
# Residuals beyond this many robust sigmas are dropped before the refit.
_OUTLIER_SIGMAS = 2.5
# Floor on fit weights so a near-zero vega cannot produce a singular system.
_MIN_WEIGHT = 1e-6
# Contracts nearest the forward used to anchor the ATM vol for the fit band;
# fewer usable candidates than this minimum means no band can be estimated.
_ANCHOR_POINTS = 7
_MIN_ANCHOR_POINTS = 3


def _mad_sigma(residuals: np.ndarray, floor: float) -> float:
    mad = float(np.median(np.abs(residuals - np.median(residuals))))
    return max(1.4826 * mad, floor)


def infer_forward(
    chain: OptionChain,
    rate: float,
    time_to_expiry: float,
    params: AnalysisParams,
) -> tuple[float, str, int, list[ParityRecord]]:
    """Implied forward via put-call parity, plus per-strike parity records."""
    growth = math.exp(rate * time_to_expiry)
    discount = math.exp(-rate * time_to_expiry)
    spot = float(chain.spot)

    two_sided_rows = []
    candidates: list[tuple[float, float]] = []  # (|K - spot|, F_K)
    for row in chain.rows:
        c, p = row.call, row.put
        if c.mid is None or p.mid is None:
            continue
        two_sided_rows.append(row)
        if (c.bid is None or c.bid <= 0.0) or (p.bid is None or p.bid <= 0.0):
            continue
        if c.ask is not None and c.ask < c.bid:
            continue
        if p.ask is not None and p.ask < p.bid:
            continue
        if not (
            spot * (1.0 - _PARITY_MONEYNESS_BAND)
            <= row.strike
            <= spot * (1.0 + _PARITY_MONEYNESS_BAND)
        ):
            continue
        f_k = (c.mid - p.mid) * growth + row.strike
        candidates.append((abs(row.strike - spot), f_k))

    candidates.sort(key=lambda t: t[0])
    used = [f for _, f in candidates[: params.near_atm_pairs]]
    n_pairs = len(used)

    forward = spot * growth
    source = "spot_carry_fallback"
    if n_pairs >= params.min_parity_pairs:
        parity_forward = float(median(used))
        if _FORWARD_SANITY_LO * spot <= parity_forward <= _FORWARD_SANITY_HI * spot:
            forward = parity_forward
            source = "parity"

    parity_records: list[ParityRecord] = []
    for row in two_sided_rows:
        c, p = row.call, row.put
        implied_f = (c.mid - p.mid) * growth + row.strike
        deviation = (c.mid - p.mid) - discount * (forward - row.strike)
        dvs: Optional[float] = None
        if (
            c.bid is not None
            and c.ask is not None
            and p.bid is not None
            and p.ask is not None
        ):
            half_spreads = (c.ask - c.bid) / 2.0 + (p.ask - p.bid) / 2.0
            if half_spreads > 0.0:
                dvs = abs(deviation) / half_spreads
        parity_records.append(
            ParityRecord(
                strike=row.strike,
                call_mid=c.mid,
                put_mid=p.mid,
                implied_forward=implied_f,
                deviation=deviation,
                deviation_vs_spread=dvs,
                check_flag=dvs is not None and dvs > 1.0,
            )
        )

    return forward, source, n_pairs, parity_records


def fit_smile(
    points: list[tuple[float, float, float]],  # (log_moneyness, iv, weight)
    params: AnalysisParams,
) -> SmileFitInfo:
    """Robust weighted polynomial fit of IV on log-moneyness.

    One outlier-rejection iteration: fit, drop residuals beyond
    ``_OUTLIER_SIGMAS`` robust sigmas, refit on the survivors.
    """
    if len(points) < params.min_fit_points:
        return SmileFitInfo(fitted=False, reason="insufficient_points")

    k = np.array([p[0] for p in points], dtype=float)
    iv = np.array([p[1] for p in points], dtype=float)
    w = np.sqrt(np.maximum([p[2] for p in points], _MIN_WEIGHT))

    span = float(k.max() - k.min())
    if span < 0.005:
        return SmileFitInfo(fitted=False, reason="degenerate_k_range")
    degree = params.fit_degree if span >= 0.02 else 1
    degree = min(degree, len(points) - 2)

    coeffs = np.polyfit(k, iv, degree, w=w)
    residuals = iv - np.polyval(coeffs, k)
    sigma = _mad_sigma(residuals, params.mad_floor)

    keep = np.abs(residuals) <= _OUTLIER_SIGMAS * sigma
    n_dropped = int(np.count_nonzero(~keep))
    if n_dropped > 0 and int(keep.sum()) >= max(params.min_fit_points, degree + 2):
        k, iv, w = k[keep], iv[keep], w[keep]
        coeffs = np.polyfit(k, iv, degree, w=w)
        residuals = iv - np.polyval(coeffs, k)
    else:
        n_dropped = 0

    sigma = _mad_sigma(residuals, params.mad_floor)
    return SmileFitInfo(
        fitted=True,
        degree=int(degree),
        coefficients=[float(c) for c in coeffs],
        n_used=int(len(k)),
        n_dropped=n_dropped,
        rmse=float(np.sqrt(np.mean(residuals**2))),
        sigma_mad=float(sigma),
        k_min=float(k.min()),
        k_max=float(k.max()),
    )


def analyze_chain(
    chain: OptionChain,
    rate: float,
    rate_source: str,
    params: Optional[AnalysisParams] = None,
    asof: Optional[date] = None,
) -> ChainAnalysis:
    params = params if params is not None else AnalysisParams()
    spot = float(chain.spot)
    if not (math.isfinite(spot) and spot > 0.0):
        # A NaN spot would otherwise propagate silently into every
        # log-moneyness; a zero spot crashes on log(K / forward).
        raise ValueError(f"invalid spot price {spot} for {chain.symbol}")
    if asof is None:
        asof = datetime.now(timezone.utc).date()
    dte_days = (chain.expiry - asof).days
    if dte_days <= 0:
        raise ValueError(
            f"expiry {chain.expiry.isoformat()} is not after asof {asof.isoformat()}"
        )
    T = dte_days / 365.0

    forward, forward_source, n_pairs, parity_records = infer_forward(
        chain, rate, T, params
    )

    contracts: list[ContractAnalysis] = []
    for row in chain.rows:
        for opt_type, quote in ((OptionType.CALL, row.call), (OptionType.PUT, row.put)):
            contract = _analyze_contract(
                quote, opt_type, forward, rate, T, params
            )
            if contract is not None:
                contracts.append(contract)

    band = _fit_band(contracts, T, params)
    if band is not None:
        for i, c in enumerate(contracts):
            if abs(c.log_moneyness) > band:
                contracts[i] = c.model_copy(
                    update={
                        "used_in_fit": False,
                        "filters_failed": [*c.filters_failed, "far_otm"],
                    }
                )

    fit_points = [
        (c.log_moneyness, c.iv, c.vega if c.vega is not None else 0.0)
        for c in contracts
        if c.used_in_fit
    ]
    fit = fit_smile(fit_points, params)

    flagged_count = 0
    if fit.fitted:
        for i, c in enumerate(contracts):
            contracts[i] = _apply_fit(c, fit, forward, rate, T, params)
            if contracts[i].verdict is not None:
                flagged_count += 1

    return ChainAnalysis.build(
        symbol=chain.symbol,
        expiry=chain.expiry,
        spot=float(chain.spot),
        forward=float(forward),
        forward_source=forward_source,
        n_parity_pairs=n_pairs,
        risk_free_rate=float(rate),
        rate_source=rate_source,
        time_to_expiry=T,
        params=params,
        fit=fit,
        contracts=contracts,
        parity=parity_records,
        flagged_count=flagged_count,
        chain_cached_at=chain.cached_at,
    )


def _fit_band(
    contracts: list[ContractAnalysis], T: float, params: AnalysisParams
) -> Optional[float]:
    """Half-width of the |log-moneyness| band the fit and flags live in.

    Anchored at the median model IV of the contracts nearest the forward;
    None when too few clean near-ATM IVs exist to estimate one (degraded
    chains keep the unbanded behavior rather than banding on noise).
    """
    candidates = [
        c
        for c in contracts
        if c.used_in_fit  # OTM, model IV, clean two-sided quote
    ]
    candidates.sort(key=lambda c: abs(c.log_moneyness))
    anchor = [c.iv for c in candidates[:_ANCHOR_POINTS] if c.iv is not None]
    if len(anchor) < _MIN_ANCHOR_POINTS:
        return None
    atm_iv = float(median(anchor))
    return max(params.fit_band_stdevs * atm_iv * math.sqrt(T), params.min_fit_band)


def _analyze_contract(
    quote: OptionQuote,
    opt_type: OptionType,
    forward: float,
    rate: float,
    T: float,
    params: AnalysisParams,
) -> Optional[ContractAnalysis]:
    # Sides with no quote data at all carry no information; skip them.
    if quote.bid is None and quote.ask is None and quote.mid is None and quote.iv is None:
        return None

    K = float(quote.strike)
    is_otm = K >= forward if opt_type is OptionType.CALL else K < forward

    rel_spread: Optional[float] = None
    if (
        quote.bid is not None
        and quote.ask is not None
        and quote.mid is not None
        and quote.mid > 0.0
    ):
        rel_spread = (quote.ask - quote.bid) / quote.mid

    iv: Optional[float] = None
    iv_source = "none"
    vega: Optional[float] = None
    if quote.mid is not None and quote.mid > 0.0:
        result = implied_vol_black76(quote.mid, forward, K, T, rate, opt_type)
        iv_status = result.status
        if result.status == "ok":
            iv = result.iv
            vega = result.vega
            iv_source = "model"
    else:
        iv_status = "no_mid"
    if iv is None and quote.iv is not None and quote.iv > 0.0:
        iv = float(quote.iv)
        iv_source = "yfinance"

    filters_failed: list[str] = []
    if quote.bid is None or quote.bid <= 0.0:
        filters_failed.append("no_bid")
    if quote.bid is not None and quote.ask is not None and quote.ask < quote.bid:
        filters_failed.append("crossed")
    if rel_spread is None or rel_spread > params.max_rel_spread:
        filters_failed.append("wide_spread")
    oi = quote.open_interest if quote.open_interest is not None else 0
    vol = quote.volume if quote.volume is not None else 0
    if oi < params.min_open_interest and vol < params.min_volume:
        filters_failed.append("low_liquidity")
    if not is_otm:
        filters_failed.append("itm")
    if iv_source != "model":
        filters_failed.append("iv_unsolved")

    # Fit membership needs trustworthy prices (OTM, solved IV, clean two-sided
    # quote); low open interest alone does not distort a mid, so the liquidity
    # gate applies only to flagging, not fitting.
    used_in_fit = (
        is_otm
        and iv_source == "model"
        and not any(
            f in filters_failed for f in ("no_bid", "crossed", "wide_spread")
        )
    )

    return ContractAnalysis(
        strike=K,
        type=opt_type.value,
        bid=quote.bid,
        ask=quote.ask,
        mid=quote.mid,
        rel_spread=rel_spread,
        open_interest=quote.open_interest,
        volume=quote.volume,
        is_otm=is_otm,
        log_moneyness=math.log(K / forward),
        iv=iv,
        iv_source=iv_source,
        iv_status=iv_status,
        vega=vega,
        used_in_fit=used_in_fit,
        filters_failed=filters_failed,
    )


def _apply_fit(
    c: ContractAnalysis,
    fit: SmileFitInfo,
    forward: float,
    rate: float,
    T: float,
    params: AnalysisParams,
) -> ContractAnalysis:
    # Never extrapolate: outside the fitted strike range the polynomial says
    # nothing about fair IV, and wing misfit would masquerade as mispricing.
    if not (fit.k_min <= c.log_moneyness <= fit.k_max):
        return c
    fitted_iv = float(np.polyval(np.array(fit.coefficients), c.log_moneyness))
    if fitted_iv <= 0.0:
        # Polynomial extrapolation dipped non-physical; nothing to compare to.
        return c

    opt_type = OptionType(c.type)
    fitted_price = black76_price(forward, c.strike, T, rate, fitted_iv, opt_type)

    update: dict = {"fitted_iv": fitted_iv, "fitted_price": fitted_price}

    if c.mid is not None:
        update["price_edge"] = c.mid - fitted_price

    filters = list(c.filters_failed)
    half_spread: Optional[float] = None
    if c.bid is not None and c.ask is not None:
        half_spread = (c.ask - c.bid) / 2.0
    if (
        "price_edge" in update
        and half_spread is not None
        and abs(update["price_edge"]) <= half_spread
    ):
        # Fitted fair value sits inside the quoted market: no material edge.
        filters.append("inside_spread")
    update["filters_failed"] = filters

    if c.iv_source == "model" and fit.sigma_mad:
        residual = c.iv - fitted_iv
        z = residual / fit.sigma_mad
        update["residual"] = residual
        update["z"] = z
        if c.is_otm and abs(z) >= params.z_threshold and not filters:
            update["verdict"] = "rich" if z > 0 else "cheap"

    return c.model_copy(update=update)
