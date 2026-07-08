"""Scanner alert feed and manual scan trigger."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.analysis import AlertsResponse, ScannerStatus, market_open

from .limits import RATE_LIMIT_DATA, limiter

router = APIRouter(tags=["alerts"])
logger = logging.getLogger("app.api.alerts")


def _disabled_response() -> AlertsResponse:
    return AlertsResponse(
        status=ScannerStatus(
            enabled=False,
            market_open=market_open(),
            scanning=False,
            watchlist=[],
            interval_seconds=0,
            persistence_scans=0,
        ),
        active=[],
        pending=[],
        resolved=[],
    )


@router.get("/alerts", response_model=AlertsResponse)
@limiter.limit(RATE_LIMIT_DATA)
async def get_alerts(request: Request) -> AlertsResponse:
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is None:
        return _disabled_response()
    return scanner.snapshot()


@router.post("/alerts/scan", response_model=AlertsResponse, status_code=202)
@limiter.limit(RATE_LIMIT_DATA)
async def trigger_scan(request: Request) -> AlertsResponse:
    """Kick off a sweep in the background (also usable while the market is
    closed). A full sweep takes 30-90s of throttled Yahoo fetches, so it must
    not run inline in the request; poll GET /alerts for completion
    (status.scanning goes false)."""
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is None:
        raise HTTPException(
            status_code=503,
            detail="Scanner is disabled (set OFV_SCANNER_ENABLED=1 to enable)",
        )
    scanner.request_scan()  # no-op if a sweep is already running
    return scanner.snapshot()
