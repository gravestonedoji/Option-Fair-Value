"""Tests for app.data.fred_client.FredClient.

Network tests are skipped unless OFV_RUN_NETWORK_TESTS=1 and FRED_API_KEY is set.
The constructor-validation test runs unconditionally (no network needed).
"""
from __future__ import annotations

import os

import pytest

_RUN = os.environ.get("OFV_RUN_NETWORK_TESTS") == "1"
_HAS_KEY = bool(os.environ.get("FRED_API_KEY"))


def test_missing_api_key_raises_value_error(monkeypatch):
    """Constructor must raise ValueError when no key is provided anywhere."""
    from app.data.fred_client import FredClient
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(ValueError):
        FredClient(api_key=None, cache=None)


@pytest.mark.skipif(
    not (_RUN and _HAS_KEY),
    reason="requires network + FRED_API_KEY (set OFV_RUN_NETWORK_TESTS=1 and FRED_API_KEY)",
)
@pytest.mark.asyncio
async def test_get_risk_free_rate_is_sane_float():
    from app.data.fred_client import FredClient
    c = FredClient()
    r = await c.get_risk_free_rate()
    assert isinstance(r, float)
    assert 0.0 <= r <= 0.20
