"""Pydantic models for chain mispricing analysis.

These double as the API response models (the analysis router returns them
directly), mirrored field-for-field in ``frontend/src/types.ts``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisParams(BaseModel):
    z_threshold: float = 2.0
    max_rel_spread: float = 0.25
    min_open_interest: int = 10
    min_volume: int = 10
    min_fit_points: int = 5
    fit_degree: int = 2
    near_atm_pairs: int = 11
    min_parity_pairs: int = 3
    mad_floor: float = 0.005  # vol points; floors the robust residual scale
    # Fit/flag only within |ln(K/F)| <= fit_band_stdevs * atm_iv * sqrt(T)
    # (floored at min_fit_band): a low-degree polynomial cannot represent the
    # far wings, and misfit there masquerades as mispricing.
    fit_band_stdevs: float = 4.0
    min_fit_band: float = 0.02


class ContractAnalysis(BaseModel):
    strike: float
    type: Literal["call", "put"]
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    rel_spread: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    is_otm: bool
    log_moneyness: float  # ln(K / F)
    iv: Optional[float] = None
    iv_source: Literal["model", "yfinance", "none"]
    iv_status: str  # IVResult.status, or "no_mid" when there was no mid to solve
    vega: Optional[float] = None
    fitted_iv: Optional[float] = None
    residual: Optional[float] = None  # iv - fitted_iv, model-solved IVs only
    z: Optional[float] = None
    fitted_price: Optional[float] = None
    price_edge: Optional[float] = None  # mid - fitted_price
    used_in_fit: bool = False
    filters_failed: list[str] = []
    verdict: Optional[Literal["rich", "cheap"]] = None


class ParityRecord(BaseModel):
    strike: float
    call_mid: Optional[float] = None
    put_mid: Optional[float] = None
    implied_forward: Optional[float] = None  # (C - P) * e^{rT} + K
    deviation: Optional[float] = None  # (C - P) - e^{-rT}(F - K), in dollars
    deviation_vs_spread: Optional[float] = None  # |deviation| / summed half-spreads
    check_flag: bool = False  # data-quality check, NOT an arbitrage signal


class SmileFitInfo(BaseModel):
    fitted: bool
    reason: Optional[Literal["insufficient_points", "degenerate_k_range"]] = None
    degree: Optional[int] = None
    # numpy polyfit convention: highest power first (also documented in types.ts)
    coefficients: list[float] = []
    n_used: int = 0
    n_dropped: int = 0
    rmse: Optional[float] = None
    sigma_mad: Optional[float] = None
    k_min: Optional[float] = None
    k_max: Optional[float] = None


class ChainAnalysis(BaseModel):
    symbol: str
    expiry: date
    spot: float
    forward: float
    forward_source: Literal["parity", "spot_carry_fallback"]
    n_parity_pairs: int
    risk_free_rate: float
    rate_source: Literal["fred", "fallback"]
    time_to_expiry: float
    params: AnalysisParams
    fit: SmileFitInfo
    contracts: list[ContractAnalysis]
    parity: list[ParityRecord]
    flagged_count: int
    chain_cached_at: datetime
    computed_at: datetime

    @classmethod
    def build(cls, **kwargs) -> "ChainAnalysis":
        kwargs.setdefault("computed_at", _utcnow())
        return cls(**kwargs)
