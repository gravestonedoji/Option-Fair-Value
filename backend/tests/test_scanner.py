"""Offline tests for the background mispricing scanner (stubbed data layer)."""
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.analysis import Scanner, ScannerConfig, market_open
from app.analysis.scanner import next_market_open
from app.data.cache import Cache
from app.data.models import DataError, Expiries
from app.pricing.black_scholes import OptionType
from app.pricing.implied_vol import black76_price

from tests.test_mispricing import _RATE, _requote, _smile_iv, make_synthetic_chain

_ET = ZoneInfo("America/New_York")
_TODAY = datetime.now(timezone.utc).astimezone(_ET).date()
_DTE = 30
_EXPIRY = _TODAY + timedelta(days=_DTE)

_CONFIG = ScannerConfig(
    watchlist=("SYN",),
    interval_seconds=600,
    persistence_scans=2,
    min_dte=1,
    max_dte=90,
    max_expiries=4,
    throttle_seconds=0.0,
)


def _clean_chain():
    return make_synthetic_chain(asof=_TODAY, dte_days=_DTE)


def _rich_chain():
    """Synthetic chain with the 115 call bumped 4 vol points rich."""
    chain = _clean_chain()
    K = 115.0
    T = _DTE / 365.0
    forward = 100.0 * math.exp(_RATE * T)
    k = math.log(K / forward)
    bumped = black76_price(forward, K, T, _RATE, _smile_iv(k) + 0.04, OptionType.CALL)
    _requote(next(r for r in chain.rows if r.strike == K), "call", bumped)
    return chain


class StubYFinance:
    def __init__(self, chain, expiries=None):
        self.chain = chain
        self.expiries = expiries if expiries is not None else [_EXPIRY]
        self.chain_error = None
        self.expiries_error = None
        self.chain_calls = 0

    async def get_expiries(self, symbol):
        if self.expiries_error is not None:
            raise self.expiries_error
        return Expiries.build(symbol=symbol, expiries=self.expiries)

    async def get_chain(self, symbol, expiry):
        self.chain_calls += 1
        if self.chain_error is not None:
            raise self.chain_error
        return self.chain


def _make_scanner(stub, cache=None, config=_CONFIG):
    return Scanner(yfinance=stub, cache=cache, fred=None, config=config)


# --- market hours -------------------------------------------------------------


def test_market_open_regular_session():
    tuesday = date(2026, 7, 7)  # a Tuesday
    assert market_open(datetime(2026, 7, 7, 10, 0, tzinfo=_ET))
    assert market_open(datetime(2026, 7, 7, 9, 30, tzinfo=_ET))
    assert not market_open(datetime(2026, 7, 7, 9, 29, tzinfo=_ET))
    assert not market_open(datetime(2026, 7, 7, 16, 0, tzinfo=_ET))
    assert not market_open(datetime(2026, 7, 11, 12, 0, tzinfo=_ET))  # Saturday
    assert tuesday.weekday() == 1


def test_market_open_converts_from_utc():
    # 15:00 UTC on a July Tuesday is 11:00 ET (EDT): open.
    assert market_open(datetime(2026, 7, 7, 15, 0, tzinfo=timezone.utc))
    # 01:00 UTC is 21:00 ET the previous evening: closed.
    assert not market_open(datetime(2026, 7, 8, 1, 0, tzinfo=timezone.utc))


def test_next_market_open_projection():
    def et(y, m, d, hh, mm):
        return datetime(y, m, d, hh, mm, tzinfo=_ET)

    # Friday 20:00 ET -> Monday 09:30 ET
    assert next_market_open(et(2026, 7, 10, 20, 0)).astimezone(_ET) == et(2026, 7, 13, 9, 30)
    # Tuesday 08:00 ET (pre-open) -> same day 09:30 ET
    assert next_market_open(et(2026, 7, 7, 8, 0)).astimezone(_ET) == et(2026, 7, 7, 9, 30)
    # Tuesday 17:00 ET (post-close) -> Wednesday 09:30 ET
    assert next_market_open(et(2026, 7, 7, 17, 0)).astimezone(_ET) == et(2026, 7, 8, 9, 30)


# --- alert state machine -------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_goes_pending_then_active():
    scanner = _make_scanner(StubYFinance(_rich_chain()))

    await scanner.scan_once()
    snap = scanner.snapshot()
    assert len(snap.pending) == 1 and len(snap.active) == 0
    assert snap.pending[0].streak == 1
    assert snap.pending[0].verdict == "rich"
    assert (snap.pending[0].type, snap.pending[0].strike) == ("call", 115.0)

    await scanner.scan_once()
    snap = scanner.snapshot()
    assert len(snap.active) == 1 and len(snap.pending) == 0
    rec = snap.active[0]
    assert rec.streak == 2
    assert rec.status == "active"


@pytest.mark.asyncio
async def test_first_seen_preserved_across_scans():
    scanner = _make_scanner(StubYFinance(_rich_chain()))
    await scanner.scan_once()
    first_seen = scanner.snapshot().pending[0].first_seen
    await scanner.scan_once()
    assert scanner.snapshot().active[0].first_seen == first_seen


@pytest.mark.asyncio
async def test_active_alert_resolves_when_flag_disappears():
    stub = StubYFinance(_rich_chain())
    scanner = _make_scanner(stub)
    await scanner.scan_once()
    await scanner.scan_once()
    assert len(scanner.snapshot().active) == 1

    stub.chain = _clean_chain()
    await scanner.scan_once()
    snap = scanner.snapshot()
    assert len(snap.active) == 0
    assert len(snap.resolved) == 1
    assert snap.resolved[0].resolved_at is not None

    # A re-flag after healing starts a fresh streak (pending, not active).
    stub.chain = _rich_chain()
    await scanner.scan_once()
    snap = scanner.snapshot()
    assert len(snap.pending) == 1 and len(snap.active) == 0
    assert snap.pending[0].streak == 1


@pytest.mark.asyncio
async def test_pending_dropped_silently_when_not_reflagged():
    stub = StubYFinance(_rich_chain())
    scanner = _make_scanner(stub)
    await scanner.scan_once()
    assert len(scanner.snapshot().pending) == 1

    stub.chain = _clean_chain()
    await scanner.scan_once()
    snap = scanner.snapshot()
    assert snap.pending == [] and snap.active == [] and snap.resolved == []


@pytest.mark.asyncio
async def test_fetch_error_does_not_resolve_active_alert():
    stub = StubYFinance(_rich_chain())
    scanner = _make_scanner(stub)
    await scanner.scan_once()
    await scanner.scan_once()
    assert len(scanner.snapshot().active) == 1

    stub.chain_error = DataError("yahoo hiccup")
    await scanner.scan_once()
    snap = scanner.snapshot()
    assert len(snap.active) == 1  # not resolved by a failed fetch
    assert snap.status.last_scan_errors
    assert snap.status.last_scan_chain_count == 0


@pytest.mark.asyncio
async def test_expiries_error_is_isolated_per_symbol():
    good = StubYFinance(_rich_chain())

    class TwoSymbolStub:
        def __init__(self):
            self.calls = []

        async def get_expiries(self, symbol):
            if symbol == "BAD":
                raise DataError("no options")
            return Expiries.build(symbol=symbol, expiries=[_EXPIRY])

        async def get_chain(self, symbol, expiry):
            self.calls.append(symbol)
            return good.chain

    stub = TwoSymbolStub()
    config = ScannerConfig(
        watchlist=("BAD", "SYN"), persistence_scans=2, min_dte=1, max_dte=90,
        throttle_seconds=0.0,
    )
    scanner = _make_scanner(stub, config=config)
    await scanner.scan_once()
    snap = scanner.snapshot()
    assert stub.calls == ["SYN"]  # BAD failed, SYN still scanned
    assert any("BAD" in e for e in snap.status.last_scan_errors)
    assert len(snap.pending) == 1


@pytest.mark.asyncio
async def test_expiry_window_selection():
    expiries = [
        _TODAY + timedelta(days=d) for d in (1, 5, 10, 40, 80, 200)
    ]
    stub = StubYFinance(_clean_chain(), expiries=expiries)
    config = ScannerConfig(
        watchlist=("SYN",), min_dte=3, max_dte=75, max_expiries=2,
        throttle_seconds=0.0,
    )
    scanner = _make_scanner(stub, config=config)
    selected = await scanner._select_expiries("SYN", _TODAY)
    assert selected == [_TODAY + timedelta(days=5), _TODAY + timedelta(days=10)]


@pytest.mark.asyncio
async def test_persistence_one_alerts_on_first_scan():
    config = ScannerConfig(
        watchlist=("SYN",), persistence_scans=1, min_dte=1, max_dte=90,
        throttle_seconds=0.0,
    )
    scanner = _make_scanner(StubYFinance(_rich_chain()), config=config)
    await scanner.scan_once()
    snap = scanner.snapshot()
    assert len(snap.active) == 1 and snap.pending == []
    assert snap.active[0].streak == 1


@pytest.mark.asyncio
async def test_alert_resolves_when_symbol_leaves_watchlist(tmp_path):
    cache = Cache(db_path=tmp_path / "scanner.sqlite")
    scanner = _make_scanner(StubYFinance(_rich_chain()), cache=cache)
    await scanner.scan_once()
    await scanner.scan_once()
    assert len(scanner.snapshot().active) == 1

    # Restart with SYN gone from the watchlist: the restored active alert
    # must resolve as stale, not sit frozen at the top of the panel forever.
    config = ScannerConfig(
        watchlist=("OTHER",), persistence_scans=2, min_dte=1, max_dte=90,
        throttle_seconds=0.0,
    )
    reborn = Scanner(
        yfinance=StubYFinance(_clean_chain()), cache=cache, fred=None, config=config
    )
    assert len(reborn.snapshot().active) == 1  # restored
    await reborn.scan_once()
    snap = reborn.snapshot()
    assert snap.active == []
    assert len(snap.resolved) == 1 and snap.resolved[0].resolved_at is not None


@pytest.mark.asyncio
async def test_alert_resolves_when_expiry_leaves_dte_window(tmp_path):
    cache = Cache(db_path=tmp_path / "scanner.sqlite")
    scanner = _make_scanner(StubYFinance(_rich_chain()), cache=cache)
    await scanner.scan_once()
    await scanner.scan_once()
    assert len(scanner.snapshot().active) == 1

    # Same watchlist, but the alert's expiry (30 DTE) now falls outside the
    # scan window: resolve as stale instead of freezing.
    config = ScannerConfig(
        watchlist=("SYN",), persistence_scans=2, min_dte=40, max_dte=90,
        throttle_seconds=0.0,
    )
    reborn = Scanner(
        yfinance=StubYFinance(_rich_chain()), cache=cache, fred=None, config=config
    )
    await reborn.scan_once()
    snap = reborn.snapshot()
    assert snap.active == []
    assert len(snap.resolved) == 1


@pytest.mark.asyncio
async def test_state_survives_restart_via_cache(tmp_path):
    cache = Cache(db_path=tmp_path / "scanner.sqlite")
    stub = StubYFinance(_rich_chain())
    scanner = _make_scanner(stub, cache=cache)
    await scanner.scan_once()
    await scanner.scan_once()
    assert len(scanner.snapshot().active) == 1

    reborn = _make_scanner(StubYFinance(_clean_chain()), cache=cache)
    assert len(reborn.snapshot().active) == 1  # restored from cache
