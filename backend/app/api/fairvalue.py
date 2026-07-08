from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime
from statistics import median
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request

from .limits import RATE_LIMIT_FAIRVALUE, limiter

from app.data.models import DataError
from app.data.yfinance_client import YFinanceClient
from app.pricing import (
    ExerciseStyle as PricingExerciseStyle,
    InputBands as PricingInputBands,
    OptionInputs as PricingOptionInputs,
    OptionType as PricingOptionType,
    compute_fair_value_range,
)

from .schemas import (
    ExerciseStyle,
    FairValueRange,
    FairValueRequest,
    Greeks,
    InputBands,
    ModelRange,
    OptionInputs,
    OptionType,
)

router = APIRouter(tags=["fairvalue"])
logger = logging.getLogger("app.api.fairvalue")

_SEED = 42
_N_LHS = 200
_MC_PATHS = 50_000
_FALLBACK_IV = 0.30
# US options expire on the market's calendar day; gating on the UTC date
# would reject the front expiry from 8pm ET onward while it still trades.
_MARKET_TZ = ZoneInfo("America/New_York")

# Each computation burns ~1-2s of CPU (10M Monte Carlo sims); cap how many run
# at once so a burst of requests degrades to queueing instead of thrashing.
_PRICING_SEMAPHORE = asyncio.Semaphore(
    int(os.environ.get("OFV_MAX_CONCURRENT_PRICING", "2"))
)


@router.post("/fairvalue", response_model=FairValueRange)
@limiter.limit(RATE_LIMIT_FAIRVALUE)
async def compute_fair_value(req: FairValueRequest, request: Request) -> FairValueRange:
    symbol = req.symbol.upper().strip()
    today = datetime.now(_MARKET_TZ).date()
    dte_days = (req.expiry - today).days
    if dte_days <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"expiry {req.expiry.isoformat()} is not in the future (dte={dte_days})",
        )

    overrides = req.overrides
    yf: YFinanceClient = request.app.state.yfinance

    spot, iv = await _resolve_market_inputs(yf, symbol, req.expiry, req.strike, req.type)
    if overrides is not None and overrides.spot is not None:
        spot = overrides.spot
    if overrides is not None and overrides.volatility is not None:
        iv = overrides.volatility

    if overrides is not None and overrides.risk_free_rate is not None:
        rate = overrides.risk_free_rate
    else:
        fred = getattr(request.app.state, "fred", None)
        if fred is None:
            raise HTTPException(
                status_code=503,
                detail="risk_free_rate not overridden and FRED_API_KEY is not set on the server",
            )
        try:
            rate = await fred.get_risk_free_rate()
        except DataError as exc:
            raise HTTPException(status_code=502, detail=f"FRED error: {exc}")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"FRED error: {exc}")

    dividend_yield = overrides.dividend_yield if overrides and overrides.dividend_yield is not None else 0.0
    time_to_expiry = overrides.time_to_expiry if overrides and overrides.time_to_expiry is not None else dte_days / 365.0
    style = (overrides.style if overrides and overrides.style is not None else ExerciseStyle.AMERICAN)

    pricing_inputs = PricingOptionInputs(
        spot=float(spot),
        strike=float(req.strike),
        time_to_expiry=float(time_to_expiry),
        risk_free_rate=float(rate),
        dividend_yield=float(dividend_yield),
        volatility=float(iv),
        option_type=PricingOptionType(req.type.value),
        style=PricingExerciseStyle(style.value),
    )

    bands = PricingInputBands(
        vol_pct=float(req.bands.vol_pct),
        spot_pct=float(req.bands.spot_pct),
        rate_bps=float(req.bands.rate_bps),
        dte_days=float(req.bands.dte_days),
    )

    try:
        # numpy-heavy and synchronous: run in a worker thread so the event loop
        # stays responsive, and gate on the semaphore to bound CPU load.
        async with _PRICING_SEMAPHORE:
            fvr = await asyncio.to_thread(
                compute_fair_value_range,
                pricing_inputs,
                bands,
                n_lhs=_N_LHS,
                mc_paths=_MC_PATHS,
                seed=_SEED,
            )
    except Exception as exc:
        logger.exception("fair value computation failed")
        raise HTTPException(status_code=500, detail=f"pricing error: {exc}")

    return _to_response(fvr)


async def _resolve_market_inputs(
    yf: YFinanceClient,
    symbol: str,
    expiry: date,
    strike: float,
    opt_type: OptionType,
) -> tuple[float, float]:
    try:
        chain = await yf.get_chain(symbol, expiry)
    except DataError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"chain fetch error: {exc}")

    row = None
    for r in chain.rows:
        if abs(r.strike - strike) < 1e-6:
            row = r
            break
    if row is None:
        sample_strikes = [r.strike for r in chain.rows[:20]]
        raise HTTPException(
            status_code=404,
            detail=f"strike {strike} not in chain for {symbol} {expiry.isoformat()}; sample strikes: {sample_strikes}",
        )

    quote = row.call if opt_type == OptionType.CALL else row.put
    iv = quote.iv
    if iv is None or iv <= 0:
        all_ivs = [
            (r.call.iv if opt_type == OptionType.CALL else r.put.iv)
            for r in chain.rows
        ]
        all_ivs = [v for v in all_ivs if v is not None and v > 0]
        if all_ivs:
            iv = float(median(all_ivs))
            logger.warning(
                "IV missing for %s %s %.2f %s; using chain median %.4f",
                symbol, expiry.isoformat(), strike, opt_type.value, iv,
            )
        else:
            iv = _FALLBACK_IV
            logger.warning("No IVs in chain; using fallback %.2f", _FALLBACK_IV)
    return float(chain.spot), float(iv)


def _to_response(fvr) -> FairValueRange:
    models = {}
    for name, mr in fvr.models.items():
        g = mr.greeks
        models[name] = ModelRange(
            name=mr.name,
            base=float(mr.base),
            min=float(mr.min),
            p5=float(mr.p5),
            median=float(mr.median),
            p95=float(mr.p95),
            max=float(mr.max),
            greeks=Greeks(
                price=float(g.price),
                delta=None if g.delta is None else float(g.delta),
                gamma=None if g.gamma is None else float(g.gamma),
                theta=None if g.theta is None else float(g.theta),
                vega=None if g.vega is None else float(g.vega),
                rho=None if g.rho is None else float(g.rho),
            ),
        )

    base_results = {}
    for name, pr in fvr.base_results.items():
        base_results[name] = Greeks(
            price=float(pr.price),
            delta=None if pr.delta is None else float(pr.delta),
            gamma=None if pr.gamma is None else float(pr.gamma),
            theta=None if pr.theta is None else float(pr.theta),
            vega=None if pr.vega is None else float(pr.vega),
            rho=None if pr.rho is None else float(pr.rho),
        )

    bi = fvr.base_inputs
    base_inputs = OptionInputs(
        spot=float(bi.spot),
        strike=float(bi.strike),
        time_to_expiry=float(bi.time_to_expiry),
        risk_free_rate=float(bi.risk_free_rate),
        dividend_yield=float(bi.dividend_yield),
        volatility=float(bi.volatility),
        option_type=OptionType(bi.option_type.value),
        style=ExerciseStyle(bi.style.value),
    )

    samples = {name: [float(x) for x in arr] for name, arr in fvr.samples.items()}

    bands = InputBands(
        vol_pct=float(fvr.bands.vol_pct),
        spot_pct=float(fvr.bands.spot_pct),
        rate_bps=float(fvr.bands.rate_bps),
        dte_days=float(fvr.bands.dte_days),
    )

    return FairValueRange(
        models=models,
        bands=bands,
        base_inputs=base_inputs,
        base_results=base_results,
        samples=samples,
    )
