"""Pydantic v2 schemas and shared exceptions for the data layer.

These models are the API contract that other modules (pricing, API routes)
import. Keep fields stable; additions are fine, removals/renames are breaking.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, Field


class DataError(Exception):
    """Raised by data clients when a fetch fails or returns no usable data."""


def _utcnow() -> datetime:
    """Timezone-aware UTC now; isolated for testability."""
    return datetime.now(timezone.utc)


class OptionQuote(BaseModel):
    strike: float
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    iv: float | None = None            # implied vol, decimal (0.20 = 20%)
    open_interest: int | None = None
    volume: int | None = None
    in_the_money: bool | None = None


class OptionChainRow(BaseModel):
    strike: float
    call: OptionQuote
    put: OptionQuote


class OptionChain(BaseModel):
    symbol: str
    expiry: date
    spot: float
    rows: list[OptionChainRow]
    cached_at: datetime                 # timezone-aware UTC

    @classmethod
    def build(cls, **kwargs) -> "OptionChain":
        kwargs.setdefault("cached_at", _utcnow())
        return cls(**kwargs)


class Expiries(BaseModel):
    symbol: str
    expiries: list[date]
    cached_at: datetime                 # timezone-aware UTC

    @classmethod
    def build(cls, **kwargs) -> "Expiries":
        kwargs.setdefault("cached_at", _utcnow())
        return cls(**kwargs)
