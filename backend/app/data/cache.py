"""SQLite-backed TTL cache for the data layer.

Design goals:
* Pickle-serialized values, single-row table with expiry timestamp.
* Thread-safe via a per-instance threading.Lock around the SQLite connection.
* Graceful degradation: if the DB is corrupt or unwritable, the cache logs a
  warning and silently degrades to a no-op (``get`` returns None, ``set`` is a
  no-op, ``purge_expired`` is a no-op). It never raises.
* Opportunistic purge: every ``get`` purges expired rows before answering.
"""
from __future__ import annotations

import logging
import os
import pickle
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("app.data.cache")

# --- TTL policy (seconds) ----------------------------------------------------
TTL_QUOTES = 60          # option quotes / chain rows
TTL_EXPIRIES = 86400     # list of expiries for a symbol (24h)
TTL_RATE = 3600          # risk-free rate (1h)

DEFAULT_DB_PATH = Path.home() / ".option_fair_value" / "cache.sqlite"

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


# --- Cache key builders ------------------------------------------------------
def make_chain_key(symbol: str, expiry_iso: str) -> str:
    return f"chain:{symbol.upper()}:{expiry_iso}"


def make_expiries_key(symbol: str) -> str:
    return f"expiries:{symbol.upper()}"


def make_rate_key() -> str:
    return "rate:risk_free"


# --- Helpers -----------------------------------------------------------------
def _now_ms() -> int:
    return int(time.time() * 1000)


class Cache:
    """SQLite-backed TTL cache.

    Parameters
    ----------
    db_path:
        Location of the SQLite file. Parent directory is created on init.
        Defaults to ``~/.option_fair_value/cache.sqlite``.
    """

    def __init__(self, db_path: Optional[os.PathLike] = None) -> None:
        self._db_path: Path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._healthy: bool = False
        self._open()

    # --- connection management ----------------------------------------------
    def _open(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.commit()
            self._conn = conn
            self._healthy = True
        except Exception as exc:  # noqa: BLE001 - we degrade on any failure
            logger.warning("Cache at %s unavailable: %s", self._db_path, exc)
            self._close_quietly()
            self._conn = None
            self._healthy = False

    def _close_quietly(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass

    def __del__(self) -> None:
        try:
            self._close_quietly()
        except Exception:  # noqa: BLE001
            pass

    # --- core ops ------------------------------------------------------------
    def get(self, key: str) -> Any | None:
        """Return the (deserialized) value if present and unexpired, else None.

        Also opportunistically purges expired rows.
        """
        if not self._healthy or self._conn is None:
            return None
        with self._lock:
            try:
                self._purge_expired_locked()
                cur = self._conn.execute(
                    "SELECT value FROM cache WHERE key = ? AND expires_at >= ?",
                    (key, _now_ms()),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                try:
                    return pickle.loads(row[0])
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Cache entry %s could not be deserialized: %s", key, exc)
                    self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                    self._conn.commit()
                    return None
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cache.get failed (%s): %s", key, exc)
                self._mark_broken()
                return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Serialize ``value`` with pickle and store it with the given TTL."""
        if not self._healthy or self._conn is None:
            return None
        if ttl_seconds < 0:
            return None
        payload = pickle.dumps(value)
        now_ms = _now_ms()
        expires_at = now_ms + int(ttl_seconds * 1000)
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, expires_at, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (key, payload, expires_at, now_ms),
                )
                self._conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cache.set failed (%s): %s", key, exc)
                self._mark_broken()
                return None

    def purge_expired(self) -> None:
        """Delete all expired rows."""
        if not self._healthy or self._conn is None:
            return None
        with self._lock:
            try:
                self._purge_expired_locked()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cache.purge_expired failed: %s", exc)
                self._mark_broken()

    def _purge_expired_locked(self) -> None:
        assert self._conn is not None
        self._conn.execute("DELETE FROM cache WHERE expires_at < ?", (_now_ms(),))
        self._conn.commit()

    def _mark_broken(self) -> None:
        self._close_quietly()
        self._conn = None
        self._healthy = False

    # --- context manager support -------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._close_quietly()
            self._conn = None
            self._healthy = False

    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
