"""Background mispricing scanner with persistence-based alerting.

Sweeps a watchlist across near-dated expiries on an interval (market hours
only), reusing :func:`app.analysis.analyze_chain`. A contract only becomes an
*active* alert after being flagged in ``persistence_scans`` consecutive scans
— single-snapshot flags are routinely one-tick quote glitches on delayed
data, and alerting on them would train the user to ignore the panel.

Alert lifecycle: pending (streak < N) -> active (streak >= N) -> resolved
(scanned again and no longer flagged). Pending entries that vanish are
dropped silently; resolved ones are kept for a retention window so the UI
can show what recently healed.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.data.cache import Cache, make_scanner_state_key
from app.data.yfinance_client import YFinanceClient

from .mispricing import analyze_chain
from .models import AnalysisParams, ChainAnalysis, ContractAnalysis

logger = logging.getLogger("app.analysis.scanner")

_MARKET_TZ = ZoneInfo("America/New_York")
_MARKET_OPEN = time(9, 30)
_MARKET_CLOSE = time(16, 0)
# Persisted-state TTL: long enough to survive restarts, short enough that a
# machine left off for a week doesn't resurrect stale alerts.
_STATE_TTL_SECONDS = 7 * 86400
# Cadence of the "is the market open yet" check while closed.
_CLOSED_POLL_SECONDS = 60


def market_open(now: Optional[datetime] = None) -> bool:
    """US equity regular session: Mon-Fri 9:30-16:00 ET (holidays ignored)."""
    if now is None:
        now = datetime.now(_MARKET_TZ)
    else:
        now = now.astimezone(_MARKET_TZ)
    if now.weekday() >= 5:
        return False
    return _MARKET_OPEN <= now.time() < _MARKET_CLOSE


def next_market_open(now: Optional[datetime] = None) -> datetime:
    """UTC timestamp of the next regular-session open (holidays ignored)."""
    et = (now if now is not None else datetime.now(_MARKET_TZ)).astimezone(_MARKET_TZ)
    candidate = et.date()
    if et.time() >= _MARKET_OPEN:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    open_et = datetime.combine(candidate, _MARKET_OPEN, tzinfo=_MARKET_TZ)
    return open_et.astimezone(timezone.utc)


@dataclass(frozen=True)
class ScannerConfig:
    watchlist: tuple[str, ...] = ("SPY", "QQQ", "AAPL", "NVDA")
    interval_seconds: int = 600
    persistence_scans: int = 2
    min_dte: int = 3
    max_dte: int = 75
    max_expiries: int = 4
    throttle_seconds: float = 1.5
    resolved_retention_hours: int = 24

    @classmethod
    def from_env(cls) -> "ScannerConfig":
        raw = os.environ.get("OFV_SCANNER_WATCHLIST", "")
        watchlist = tuple(
            s.strip().upper() for s in raw.split(",") if s.strip()
        ) or cls.watchlist

        def _int(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, default))
            except ValueError:
                logger.warning("Ignoring non-integer %s; using %d", name, default)
                return default

        return cls(
            watchlist=watchlist,
            interval_seconds=_int("OFV_SCANNER_INTERVAL", cls.interval_seconds),
            persistence_scans=_int("OFV_SCANNER_PERSISTENCE", cls.persistence_scans),
            min_dte=_int("OFV_SCANNER_MIN_DTE", cls.min_dte),
            max_dte=_int("OFV_SCANNER_MAX_DTE", cls.max_dte),
            max_expiries=_int("OFV_SCANNER_MAX_EXPIRIES", cls.max_expiries),
        )


class AlertRecord(BaseModel):
    key: str  # "SYMBOL:expiry:type:strike"
    symbol: str
    expiry: date
    type: str  # "call" | "put"
    strike: float
    verdict: str  # "rich" | "cheap"
    z: float
    price_edge: Optional[float] = None
    mid: Optional[float] = None
    fitted_price: Optional[float] = None
    iv: Optional[float] = None
    fitted_iv: Optional[float] = None
    rel_spread: Optional[float] = None
    open_interest: Optional[int] = None
    status: str  # "pending" | "active" | "resolved"
    streak: int
    first_seen: datetime
    last_seen: datetime
    resolved_at: Optional[datetime] = None


class ScannerStatus(BaseModel):
    enabled: bool
    market_open: bool
    scanning: bool
    watchlist: list[str]
    interval_seconds: int
    persistence_scans: int
    last_scan_started: Optional[datetime] = None
    last_scan_completed: Optional[datetime] = None
    last_scan_chain_count: int = 0
    last_scan_errors: list[str] = []
    next_scan_at: Optional[datetime] = None


class AlertsResponse(BaseModel):
    status: ScannerStatus
    active: list[AlertRecord]
    pending: list[AlertRecord]
    resolved: list[AlertRecord]


def _contract_key(symbol: str, expiry: date, c: ContractAnalysis) -> str:
    return f"{symbol}:{expiry.isoformat()}:{c.type}:{c.strike:g}"


class Scanner:
    def __init__(
        self,
        yfinance: YFinanceClient,
        cache: Optional[Cache],
        fred=None,
        config: Optional[ScannerConfig] = None,
        params: Optional[AnalysisParams] = None,
        fallback_rate: float = 0.04,
    ) -> None:
        self._yf = yfinance
        self._cache = cache
        self._fred = fred
        self.config = config if config is not None else ScannerConfig.from_env()
        self._params = params if params is not None else AnalysisParams()
        self._fallback_rate = fallback_rate

        self._state: dict[str, AlertRecord] = {}
        self._task: Optional[asyncio.Task] = None
        self._manual_task: Optional[asyncio.Task] = None
        self._scan_lock = asyncio.Lock()
        self._scanning = False
        self._last_scan_started: Optional[datetime] = None
        self._last_scan_completed: Optional[datetime] = None
        self._last_scan_chain_count = 0
        self._last_scan_errors: list[str] = []
        self._next_scan_at: Optional[datetime] = None

        self._load_state()

    # --- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._loop())
            logger.info(
                "Scanner started: watchlist=%s interval=%ss persistence=%s",
                ",".join(self.config.watchlist),
                self.config.interval_seconds,
                self.config.persistence_scans,
            )

    async def stop(self) -> None:
        for task in (self._task, self._manual_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = None
        self._manual_task = None

    def request_scan(self) -> bool:
        """Kick off a sweep in the background; False if one is already running.

        A full sweep takes 30-90s of throttled Yahoo fetches — far too long to
        run inline in a request handler.
        """
        if self._scan_lock.locked() or (
            self._manual_task is not None and not self._manual_task.done()
        ):
            return False
        self._manual_task = asyncio.get_running_loop().create_task(self.scan_once())
        return True

    async def _loop(self) -> None:
        while True:
            try:
                if market_open():
                    await self.scan_once()
                    delay = self.config.interval_seconds
                    self._next_scan_at = _utcnow() + timedelta(seconds=delay)
                else:
                    delay = _CLOSED_POLL_SECONDS
                    # The next *scan* is at the open, not the next poll.
                    self._next_scan_at = next_market_open()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loop must survive anything
                logger.exception("scan cycle failed")
                delay = self.config.interval_seconds
                self._next_scan_at = _utcnow() + timedelta(seconds=delay)
            await asyncio.sleep(delay)

    # --- scanning --------------------------------------------------------
    async def scan_once(self) -> None:
        """One full watchlist sweep. Serialized: concurrent calls queue."""
        async with self._scan_lock:
            self._scanning = True
            now = _utcnow()
            self._last_scan_started = now
            errors: list[str] = []
            chains = 0
            today = datetime.now(_MARKET_TZ).date()
            rate, rate_source = await self._resolve_rate()

            flagged: dict[str, AlertRecord] = {}
            scanned_pairs: set[tuple[str, date]] = set()
            selected_expiries: dict[str, set[date]] = {}
            try:
                for symbol in self.config.watchlist:
                    try:
                        expiries = await self._select_expiries(symbol, today)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{symbol}: expiries: {exc}")
                        continue
                    selected_expiries[symbol] = set(expiries)
                    for expiry in expiries:
                        try:
                            analysis = await self._analyze(
                                symbol, expiry, rate, rate_source, today
                            )
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"{symbol} {expiry}: {exc}")
                            continue
                        chains += 1
                        scanned_pairs.add((symbol, expiry))
                        for c in analysis.contracts:
                            if c.verdict is not None and c.z is not None:
                                rec = self._make_record(symbol, expiry, c, now)
                                flagged[rec.key] = rec
                        await asyncio.sleep(self.config.throttle_seconds)

                self._update_state(flagged, scanned_pairs, selected_expiries, now, today)
                self._persist_state()
            finally:
                self._scanning = False
                self._last_scan_completed = _utcnow()
                self._last_scan_chain_count = chains
                self._last_scan_errors = errors
                if errors:
                    logger.warning("scan finished with %d errors: %s", len(errors), errors)

    async def _resolve_rate(self) -> tuple[float, str]:
        if self._fred is not None:
            try:
                return float(await self._fred.get_risk_free_rate()), "fred"
            except Exception as exc:  # noqa: BLE001
                logger.warning("FRED rate fetch failed; using fallback: %s", exc)
        return self._fallback_rate, "fallback"

    async def _select_expiries(self, symbol: str, today: date) -> list[date]:
        expiries = await self._yf.get_expiries(symbol)
        eligible = [
            e
            for e in expiries.expiries
            if self.config.min_dte <= (e - today).days <= self.config.max_dte
        ]
        return sorted(eligible)[: self.config.max_expiries]

    async def _analyze(
        self, symbol: str, expiry: date, rate: float, rate_source: str, today: date
    ) -> ChainAnalysis:
        chain = await self._yf.get_chain(symbol, expiry)
        return await asyncio.to_thread(
            analyze_chain, chain, rate, rate_source, self._params, today
        )

    def _make_record(
        self, symbol: str, expiry: date, c: ContractAnalysis, now: datetime
    ) -> AlertRecord:
        return AlertRecord(
            key=_contract_key(symbol, expiry, c),
            symbol=symbol,
            expiry=expiry,
            type=c.type,
            strike=c.strike,
            verdict=c.verdict,
            z=c.z,
            price_edge=c.price_edge,
            mid=c.mid,
            fitted_price=c.fitted_price,
            iv=c.iv,
            fitted_iv=c.fitted_iv,
            rel_spread=c.rel_spread,
            open_interest=c.open_interest,
            # With persistence <= 1, one flagged scan is already enough.
            status="active" if 1 >= self.config.persistence_scans else "pending",
            streak=1,
            first_seen=now,
            last_seen=now,
        )

    # --- alert state machine ----------------------------------------------
    def _update_state(
        self,
        flagged: dict[str, AlertRecord],
        scanned_pairs: set[tuple[str, date]],
        selected_expiries: dict[str, set[date]],
        now: datetime,
        today: date,
    ) -> None:
        for key, fresh in flagged.items():
            prev = self._state.get(key)
            if prev is None or prev.status == "resolved":
                # New alert (a healed one that re-flags starts a fresh streak).
                self._state[key] = fresh
                continue
            streak = prev.streak + 1
            status = "active" if streak >= self.config.persistence_scans else "pending"
            self._state[key] = fresh.model_copy(
                update={
                    "streak": streak,
                    "status": status,
                    "first_seen": prev.first_seen,
                }
            )

        retention = timedelta(hours=self.config.resolved_retention_hours)
        for key in list(self._state):
            rec = self._state[key]
            if key in flagged:
                continue
            if rec.expiry < today:
                del self._state[key]
                continue
            if rec.status == "resolved":
                if rec.resolved_at is not None and now - rec.resolved_at > retention:
                    del self._state[key]
                continue
            # A fetch error must not resolve a live alert — but a pair that is
            # no longer scan-eligible (symbol left the watchlist, expiry left
            # the DTE window or got displaced by nearer listings) would freeze
            # as "active" forever if we kept skipping it, so those fall
            # through and resolve as stale.
            sel = selected_expiries.get(rec.symbol)
            if rec.symbol in self.config.watchlist and sel is None:
                continue  # expiry-list fetch failed: can't judge this sweep
            if (
                sel is not None
                and rec.expiry in sel
                and (rec.symbol, rec.expiry) not in scanned_pairs
            ):
                continue  # selected pair whose chain fetch failed: keep as-is
            if rec.status == "active":
                self._state[key] = rec.model_copy(
                    update={"status": "resolved", "resolved_at": now}
                )
            else:  # pending that didn't persist: silently drop
                del self._state[key]

    # --- persistence -------------------------------------------------------
    def _persist_state(self) -> None:
        if self._cache is not None:
            self._cache.set(make_scanner_state_key(), self._state, _STATE_TTL_SECONDS)

    def _load_state(self) -> None:
        if self._cache is None:
            return
        stored = self._cache.get(make_scanner_state_key())
        if isinstance(stored, dict) and all(
            isinstance(v, AlertRecord) for v in stored.values()
        ):
            self._state = stored
            logger.info("Restored %d scanner alert(s) from cache", len(stored))

    # --- snapshot ----------------------------------------------------------
    def snapshot(self) -> AlertsResponse:
        by_status: dict[str, list[AlertRecord]] = {
            "active": [],
            "pending": [],
            "resolved": [],
        }
        for rec in self._state.values():
            by_status[rec.status].append(rec)
        by_abs_z = lambda r: -abs(r.z)  # noqa: E731
        manual_pending = self._manual_task is not None and not self._manual_task.done()
        return AlertsResponse(
            status=ScannerStatus(
                enabled=True,
                market_open=market_open(),
                scanning=self._scanning or manual_pending,
                watchlist=list(self.config.watchlist),
                interval_seconds=self.config.interval_seconds,
                persistence_scans=self.config.persistence_scans,
                last_scan_started=self._last_scan_started,
                last_scan_completed=self._last_scan_completed,
                last_scan_chain_count=self._last_scan_chain_count,
                last_scan_errors=self._last_scan_errors,
                next_scan_at=self._next_scan_at,
            ),
            active=sorted(by_status["active"], key=by_abs_z),
            pending=sorted(by_status["pending"], key=by_abs_z),
            resolved=sorted(
                by_status["resolved"],
                key=lambda r: r.resolved_at or r.last_seen,
                reverse=True,
            ),
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
