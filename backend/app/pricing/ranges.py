from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

import numpy as np
from scipy.stats import qmc

from app.pricing.black_scholes import ExerciseStyle, OptionInputs, PricerResult, price_bs
from app.pricing.binomial import _binomial_tree_price, price_binomial
from app.pricing.monte_carlo import _mc_batch_prices, price_monte_carlo


@dataclass(frozen=True)
class InputBands:
    vol_pct: float = 0.20
    spot_pct: float = 0.05
    rate_bps: float = 50
    dte_days: float = 2.0


@dataclass(frozen=True)
class ModelRange:
    name: str
    base: float
    min: float
    p5: float
    median: float
    p95: float
    max: float
    greeks: PricerResult


@dataclass(frozen=True)
class FairValueRange:
    models: dict
    bands: InputBands
    base_inputs: OptionInputs
    base_results: dict
    samples: dict


def compute_fair_value_range(
    inputs: OptionInputs,
    bands: InputBands,
    n_lhs: int = 200,
    mc_paths: int = 50_000,
    seed: Optional[int] = None,
) -> FairValueRange:
    vol_lo = inputs.volatility * (1.0 - bands.vol_pct)
    vol_hi = inputs.volatility * (1.0 + bands.vol_pct)
    spot_lo = inputs.spot * (1.0 - bands.spot_pct)
    spot_hi = inputs.spot * (1.0 + bands.spot_pct)
    rate_lo = inputs.risk_free_rate - bands.rate_bps / 10_000.0
    rate_hi = inputs.risk_free_rate + bands.rate_bps / 10_000.0
    t_lo = max(inputs.time_to_expiry - bands.dte_days / 365.0, 1e-6)
    t_hi = inputs.time_to_expiry + bands.dte_days / 365.0

    sampler = qmc.LatinHypercube(d=4, seed=seed)
    unit = sampler.random(n=n_lhs)
    scaled = qmc.scale(
        unit,
        [vol_lo, spot_lo, rate_lo, t_lo],
        [vol_hi, spot_hi, rate_hi, t_hi],
    )

    base_bs = price_bs(inputs)
    base_bin = price_binomial(inputs, steps=200)
    base_mc = price_monte_carlo(inputs, n_paths=mc_paths, seed=seed)

    base_results = {
        "black_scholes": base_bs,
        "binomial": base_bin,
        "monte_carlo": base_mc,
    }

    bs_samples = np.empty(n_lhs, dtype=float)
    bin_samples = np.empty(n_lhs, dtype=float)
    mc_samples = np.empty(n_lhs, dtype=float)

    mc_seed_offset = 0 if seed is None else seed + 1

    mc_inputs: list[OptionInputs] = []
    for i in range(n_lhs):
        vol_i, spot_i, rate_i, t_i = scaled[i]
        inp_i = replace(
            inputs,
            spot=float(spot_i),
            volatility=float(vol_i),
            risk_free_rate=float(rate_i),
            time_to_expiry=float(t_i),
            style=ExerciseStyle.EUROPEAN,
        )

        bs_samples[i] = price_bs(inp_i).price
        bin_samples[i] = _binomial_tree_price(inp_i, steps=200)
        mc_inputs.append(inp_i)

    mc_samples = _mc_batch_prices(mc_inputs, n_paths=mc_paths, seed=mc_seed_offset)

    models = {
        "black_scholes": _model_range("black_scholes", bs_samples, base_bs),
        "binomial": _model_range("binomial", bin_samples, base_bin),
        "monte_carlo": _model_range("monte_carlo", mc_samples, base_mc),
    }

    return FairValueRange(
        models=models,
        bands=bands,
        base_inputs=inputs,
        base_results=base_results,
        samples={
            "black_scholes": bs_samples,
            "binomial": bin_samples,
            "monte_carlo": mc_samples,
        },
    )


def _model_range(name: str, samples: np.ndarray, base: PricerResult) -> ModelRange:
    q = np.percentile(samples, [0.0, 5.0, 50.0, 95.0, 100.0])
    return ModelRange(
        name=name,
        base=float(base.price),
        min=float(q[0]),
        p5=float(q[1]),
        median=float(q[2]),
        p95=float(q[3]),
        max=float(q[4]),
        greeks=base,
    )
