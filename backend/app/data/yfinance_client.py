"""yfinance data client for option chains and expiries.

yfinance is synchronous and uses requests under the hood, so every call is
dispatched via :func:`asyncio.to_thread` to avoid blocking the event loop.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timezone
from typing import Any, Optional

from .cache import Cache, TTL_EXPIRIES, TTL_QUOTES, make_chain_key, make_expiries_key
from .models import DataError, Expiries, OptionChain, OptionChainRow, OptionQuote

logger = logging.getLogger("app.data.yfinance")

# yfinance option-chain DataFrame columns vary across versions; we try these
# names when mapping IV.
_IV_CANDIDATES = ("IV", "impliedVolatility", "impliedVol", "iv")


def _get_spot(ticker: Any) -> float:
    """Best-effort spot price: fast_info['last_price'] -> history(1d) Close."""
    try:
        fi = getattr(ticker, "fast_info", None)
        if fi is not None:
            try:
                last = fi["last_price"]
                if last is not None and float(last) > 0:
                    return float(last)
            except (KeyError, TypeError, ValueError):
                pass
    except Exception:  # noqa: BLE001
        pass
    try:
        hist = ticker.history(period="1d")
        if hist is not None and not hist.empty and "Close" in hist.columns:
            close = float(hist["Close"].iloc[-1])
            if math.isfinite(close) and close > 0:
                return close
    except Exception:  # noqa: BLE001
        pass
    raise DataError("Could not determine spot price")


def _row_to_quote(row: Any, strike: float, in_the_money: Optional[bool]) -> OptionQuote:
    """Build an :class:`OptionQuote` from a yfinance DataFrame row (Series)."""
    bid = row.get("bid") if hasattr(row, "get") else None
    ask = row.get("ask") if hasattr(row, "get") else None
    bid = float(bid) if bid is not None and str(bid) != "nan" else None
    ask = float(ask) if ask is not None and str(ask) != "nan" else None
    mid = ((bid + ask) / 2.0) if (bid is not None and ask is not None) else None

    iv = None
    for name in _IV_CANDIDATES:
        if hasattr(row, "get") and name in row:
            v = row.get(name)
            if v is not None and str(v) != "nan":
                try:
                    iv = float(v)
                except (TypeError, ValueError):
                    iv = None
            break

    oi = row.get("openInterest") if hasattr(row, "get") else None
    vol = row.get("volume") if hasattr(row, "get") else None
    try:
        oi = int(oi) if oi is not None and str(oi) != "nan" else None
    except (TypeError, ValueError):
        oi = None
    try:
        vol = int(vol) if vol is not None and str(vol) != "nan" else None
    except (TypeError, ValueError):
        vol = None
    return OptionQuote(
        strike=strike,
        bid=bid,
        ask=ask,
        mid=mid,
        iv=iv,
        open_interest=oi,
        volume=vol,
        in_the_money=in_the_money,
    )


def _empty_quote(strike: float, in_the_money: Optional[bool]) -> OptionQuote:
    return OptionQuote(strike=strike, in_the_money=in_the_money)


class YFinanceClient:
    """Async wrapper over :mod:`yfinance` with TTL caching."""

    def __init__(self, cache: Optional[Cache] = None) -> None:
        self._cache: Cache = cache if cache is not None else Cache()

    # --- expiries ------------------------------------------------------------
    async def get_expiries(self, symbol: str) -> Expiries:
        key = make_expiries_key(symbol)
        cached = self._cache.get(key)
        if cached is not None and isinstance(cached, Expiries):
            return cached
        options = await asyncio.to_thread(self._fetch_options, symbol)
        if not options:
            raise DataError(f"Symbol {symbol} not found or has no options")
        expiries_list = [date.fromisoformat(s) for s in options if s]
        if not expiries_list:
            raise DataError(f"No expiries for {symbol}")
        result = Expiries.build(symbol=symbol, expiries=expiries_list)
        self._cache.set(key, result, TTL_EXPIRIES)
        return result

    def _fetch_options(self, symbol: str) -> tuple[str, ...]:
        import yfinance as yf
        t = yf.Ticker(symbol)
        try:
            opts = t.options
        except Exception as exc:  # noqa: BLE001
            raise DataError(f"Symbol {symbol} not found: {exc}") from exc
        if opts is None:
            return ()
        return tuple(opts)

    # --- chain ---------------------------------------------------------------
    async def get_chain(self, symbol: str, expiry: date) -> OptionChain:
        key = make_chain_key(symbol, expiry.isoformat())
        cached = self._cache.get(key)
        if cached is not None and isinstance(cached, OptionChain):
            return cached
        calls_df, puts_df, spot = await asyncio.to_thread(
            self._fetch_chain, symbol, expiry
        )
        if calls_df is None or puts_df is None or calls_df.empty or puts_df.empty:
            raise DataError(f"No options for {symbol} expiry {expiry}")

        strikes = sorted(set(calls_df["strike"].tolist()) | set(puts_df["strike"].tolist()))
        if not strikes:
            raise DataError(f"No options for {symbol} expiry {expiry}")

        calls_indexed = (
            {float(k): v for k, v in zip(calls_df["strike"], calls_df.to_dict("records"))}
            if not calls_df.empty
            else {}
        )
        puts_indexed = (
            {float(k): v for k, v in zip(puts_df["strike"], puts_df.to_dict("records"))}
            if not puts_df.empty
            else {}
        )

        rows: list[OptionChainRow] = []
        for k in strikes:
            ks = float(k)
            c_row = calls_indexed.get(ks)
            p_row = puts_indexed.get(ks)
            c_itm = bool(c_row["inTheMoney"]) if c_row and "inTheMoney" in c_row else None
            p_itm = bool(p_row["inTheMoney"]) if p_row and "inTheMoney" in p_row else None
            call_q = _row_to_quote(c_row, ks, c_itm) if c_row else _empty_quote(ks, None)
            put_q = _row_to_quote(p_row, ks, p_itm) if p_row else _empty_quote(ks, None)
            rows.append(OptionChainRow(strike=ks, call=call_q, put=put_q))

        chain = OptionChain.build(
            symbol=symbol, expiry=expiry, spot=float(spot), rows=rows
        )
        self._cache.set(key, chain, TTL_QUOTES)
        return chain

    def _fetch_chain(self, symbol: str, expiry: date) -> tuple[Any, Any, float]:
        import yfinance as yf
        t = yf.Ticker(symbol)
        try:
            oc = t.option_chain(expiry.isoformat())
        except Exception as exc:  # noqa: BLE001
            raise DataError(f"No options for {symbol} expiry {expiry}: {exc}") from exc
        calls = getattr(oc, "calls", None)
        puts = getattr(oc, "puts", None)
        spot = _get_spot(t)
        return calls, puts, spot
