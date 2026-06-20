"""FRED client for the risk-free rate (3-month Treasury, DGS3MO).

Uses :mod:`httpx.AsyncClient` with a single retry on transient failure.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from .cache import Cache, TTL_RATE, make_rate_key
from .models import DataError

logger = logging.getLogger("app.data.fred")

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
SERIES_ID = "DGS3MO"
_RETRY_BACKOFF_SECONDS = 1.0


class FredClient:
    """Async FRED API client; inject a cache or use the default."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache: Optional[Cache] = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("FRED_API_KEY")
        if not key:
            raise ValueError("FRED_API_KEY not set")
        self._api_key = key
        self._cache: Cache = cache if cache is not None else Cache()

    async def get_risk_free_rate(self) -> float:
        """Latest DGS3MO value as a decimal (e.g. 0.045 == 4.5%).

        Cached for ``TTL_RATE`` seconds (1h).
        """
        key = make_rate_key()
        cached = self._cache.get(key)
        if cached is not None and isinstance(cached, float):
            return cached

        value = await self._fetch_latest_value()
        if value is None:
            raise DataError("FRED returned no usable value for DGS3MO")
        rate = float(value) / 100.0  # FRED reports percent
        self._cache.set(key, rate, TTL_RATE)
        return rate

    async def _fetch_latest_value(self) -> Optional[float]:
        params = {
            "series_id": SERIES_ID,
            "api_key": self._api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": "1",
        }
        import httpx

        last_exc: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(FRED_BASE, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    obs = data.get("observations") or []
                    if not obs:
                        raise DataError("FRED observations empty for DGS3MO")
                    val = obs[0].get("value")
                    if val is None or val == ".":
                        raise DataError("FRED latest observation missing value")
                    return float(val)
                # transient HTTP error -> retry once
                raise DataError(f"FRED HTTP {resp.status_code}: {resp.text[:200]}")
            except DataError as exc:
                last_exc = exc
                if attempt == 1:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                    continue
                raise
            except Exception as exc:  # noqa: BLE001 - network/parse error
                last_exc = exc
                if attempt == 1:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                    continue
                raise DataError(f"FRED fetch failed: {exc}") from exc
        if last_exc is not None:
            raise DataError(f"FRED fetch failed: {last_exc}") from last_exc
        return None
