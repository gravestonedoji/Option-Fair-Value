from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# --- option type / style ---------------------------------------------------


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class ExerciseStyle(str, Enum):
    EUROPEAN = "european"
    AMERICAN = "american"


# --- read-side schemas (mirror frontend src/types.ts) ----------------------


class OptionQuote(BaseModel):
    strike: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    iv: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    in_the_money: Optional[bool] = None


class OptionChainRow(BaseModel):
    strike: float
    call: OptionQuote
    put: OptionQuote


class OptionChain(BaseModel):
    symbol: str
    expiry: date
    spot: float
    rows: list[OptionChainRow]
    cached_at: datetime


class Expiries(BaseModel):
    symbol: str
    expiries: list[date]
    cached_at: datetime


# --- fair value request / response -----------------------------------------


class InputBands(BaseModel):
    vol_pct: float = 0.20
    spot_pct: float = 0.05
    rate_bps: float = 50.0
    dte_days: float = 2.0


class OptionInputsOverride(BaseModel):
    spot: Optional[float] = None
    strike: Optional[float] = None
    time_to_expiry: Optional[float] = None
    risk_free_rate: Optional[float] = None
    dividend_yield: Optional[float] = None
    volatility: Optional[float] = None
    option_type: Optional[OptionType] = None
    style: Optional[ExerciseStyle] = None


class FairValueRequest(BaseModel):
    symbol: str
    expiry: date
    strike: float
    type: OptionType
    bands: InputBands = Field(default_factory=InputBands)
    overrides: Optional[OptionInputsOverride] = None

    @model_validator(mode="after")
    def _check_symbol(self) -> "FairValueRequest":
        if not self.symbol or not self.symbol.strip().isalpha():
            raise ValueError("symbol must be non-empty alphabetic")
        return self


class Greeks(BaseModel):
    price: float
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None


class ModelRange(BaseModel):
    name: str
    base: float
    min: float
    p5: float
    median: float
    p95: float
    max: float
    greeks: Greeks


class OptionInputs(BaseModel):
    spot: float
    strike: float
    time_to_expiry: float
    risk_free_rate: float
    dividend_yield: float
    volatility: float
    option_type: OptionType
    style: ExerciseStyle


class FairValueRange(BaseModel):
    models: dict[str, ModelRange]
    bands: InputBands
    base_inputs: OptionInputs
    base_results: dict[str, Greeks]
    samples: dict[str, list[float]]
