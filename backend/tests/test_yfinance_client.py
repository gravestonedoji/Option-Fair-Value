"""Tests for app.data.yfinance_client.YFinanceClient.

These hit the network and are skipped unless OFV_RUN_NETWORK_TESTS=1.
"""
from __future__ import annotations

import os
from datetime import date

import pytest

from app.data.models import DataError, Expiries, OptionChain

_RUN = os.environ.get("OFV_RUN_NETWORK_TESTS") == "1"
pytestmark = pytest.mark.skipif(not _RUN, reason="requires network (set OFV_RUN_NETWORK_TESTS=1)")


@pytest.mark.asyncio
async def test_get_expiries_for_spy():
    from app.data.yfinance_client import YFinanceClient
    c = YFinanceClient()
    exp = await c.get_expiries("SPY")
    assert isinstance(exp, Expiries)
    assert exp.symbol == "SPY"
    assert len(exp.expiries) > 0
    assert all(isinstance(d, date) for d in exp.expiries)
    assert exp.cached_at is not None


@pytest.mark.asyncio
async def test_get_chain_for_spy_nearest_expiry():
    from app.data.yfinance_client import YFinanceClient
    c = YFinanceClient()
    exp = await c.get_expiries("SPY")
    nearest = min(exp.expiries, key=lambda d: abs((d - date.today()).days))
    chain = await c.get_chain("SPY", nearest)
    assert isinstance(chain, OptionChain)
    assert chain.symbol == "SPY"
    assert chain.expiry == nearest
    assert chain.spot > 0
    assert len(chain.rows) > 0
    # at least one row should have a real bid/ask/iv (calls or puts)
    found = False
    for r in chain.rows:
        for q in (r.call, r.put):
            if (q.bid is not None or q.ask is not None) and q.iv is not None:
                found = True
                break
        if found:
            break
    assert found, "no row had bid/ask + iv"


@pytest.mark.asyncio
async def test_unknown_symbol_raises_data_error():
    from app.data.yfinance_client import YFinanceClient
    c = YFinanceClient()
    with pytest.raises(DataError):
        await c.get_expiries("NOT_A_REAL_TICKER_XYZ")
