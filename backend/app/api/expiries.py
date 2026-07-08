from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.data.models import DataError
from app.data.yfinance_client import YFinanceClient

from .limits import RATE_LIMIT_DATA, limiter
from .schemas import Expiries

router = APIRouter(tags=["expiries"])


@router.get("/expiries/{symbol}", response_model=Expiries)
@limiter.limit(RATE_LIMIT_DATA)
async def get_expiries(symbol: str, request: Request) -> Expiries:
    symbol = symbol.upper().strip()
    client: YFinanceClient = request.app.state.yfinance
    try:
        return await client.get_expiries(symbol)
    except DataError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}")
