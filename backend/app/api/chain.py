from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.data.models import DataError
from app.data.yfinance_client import YFinanceClient

from .schemas import OptionChain

router = APIRouter(tags=["chain"])


@router.get("/chain/{symbol}", response_model=OptionChain)
async def get_chain(
    symbol: str,
    request: Request,
    expiry: str = Query(..., description="ISO date YYYY-MM-DD"),
) -> OptionChain:
    symbol = symbol.upper().strip()
    try:
        exp = date.fromisoformat(expiry)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"expiry must be ISO YYYY-MM-DD, got {expiry!r}"
        )
    client: YFinanceClient = request.app.state.yfinance
    try:
        return await client.get_chain(symbol, exp)
    except DataError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}")
