"""Chain-wide IV relative-value analysis endpoint.

Unlike ``/fairvalue`` (which 503s without FRED), this endpoint falls back to
``OFV_FALLBACK_RATE`` when no rate source is available: a screening signal
degrades gracefully, and the response labels the rate's provenance.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from numpy.linalg import LinAlgError

from app.analysis import AnalysisParams, ChainAnalysis, analyze_chain
from app.data.cache import TTL_QUOTES, make_analysis_key
from app.data.models import DataError
from app.data.yfinance_client import YFinanceClient

from .limits import RATE_LIMIT_DATA, limiter

router = APIRouter(tags=["analysis"])
logger = logging.getLogger("app.api.analysis")

_FALLBACK_RATE = float(os.environ.get("OFV_FALLBACK_RATE", "0.04"))
# US options expire on the market's calendar day; gating on the UTC date
# would reject the front expiry from 8pm ET onward while it still trades.
_MARKET_TZ = ZoneInfo("America/New_York")


@router.get("/analysis/{symbol}", response_model=ChainAnalysis)
@limiter.limit(RATE_LIMIT_DATA)
async def get_analysis(
    symbol: str,
    request: Request,
    expiry: str = Query(..., description="ISO date YYYY-MM-DD"),
    z_threshold: float = Query(2.0, ge=0.5, le=10.0),
    max_rel_spread: float = Query(0.25, gt=0.0, le=2.0),
    min_open_interest: int = Query(10, ge=0),
    min_volume: int = Query(10, ge=0),
) -> ChainAnalysis:
    symbol = symbol.upper().strip()
    try:
        exp = date.fromisoformat(expiry)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"expiry must be ISO YYYY-MM-DD, got {expiry!r}"
        )
    today = datetime.now(_MARKET_TZ).date()
    if (exp - today).days <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"expiry {exp.isoformat()} is not in the future",
        )

    client: YFinanceClient = request.app.state.yfinance
    try:
        chain = await client.get_chain(symbol, exp)
    except DataError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}")

    rate = _FALLBACK_RATE
    rate_source = "fallback"
    fred = getattr(request.app.state, "fred", None)
    if fred is not None:
        try:
            rate = float(await fred.get_risk_free_rate())
            rate_source = "fred"
        except Exception as exc:  # noqa: BLE001
            logger.warning("FRED rate fetch failed; using fallback %.4f: %s", _FALLBACK_RATE, exc)

    params = AnalysisParams(
        z_threshold=z_threshold,
        max_rel_spread=max_rel_spread,
        min_open_interest=min_open_interest,
        min_volume=min_volume,
    )

    cache = getattr(request.app.state, "cache", None)
    param_sig = (
        f"z{params.z_threshold}:s{params.max_rel_spread}"
        f":oi{params.min_open_interest}:v{params.min_volume}:r{rate:.4f}"
    )
    key = make_analysis_key(symbol, exp.isoformat(), chain.cached_at.isoformat(), param_sig)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None and isinstance(cached, ChainAnalysis):
            return cached

    try:
        # Pure numpy/scipy math (~ms per chain): worker thread keeps the event
        # loop responsive; no need for the Monte Carlo pricing semaphore.
        result = await asyncio.to_thread(
            analyze_chain, chain, rate, rate_source, params, today
        )
    except LinAlgError as exc:
        # LinAlgError subclasses ValueError; without this branch a numerical
        # failure would surface as an unlogged 400 blaming the client.
        logger.exception("chain analysis failed")
        raise HTTPException(status_code=500, detail=f"analysis error: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("chain analysis failed")
        raise HTTPException(status_code=500, detail=f"analysis error: {exc}")

    if cache is not None:
        cache.set(key, result, TTL_QUOTES)
    return result
