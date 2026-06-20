"""Tests for app.data.cache.Cache (no network needed)."""
from __future__ import annotations

import os
import time

import pytest

from app.data.cache import (
    Cache,
    TTL_EXPIRIES,
    TTL_QUOTES,
    TTL_RATE,
    make_chain_key,
    make_expiries_key,
    make_rate_key,
)


def test_ttl_constants():
    assert TTL_QUOTES == 60
    assert TTL_EXPIRIES == 86400
    assert TTL_RATE == 3600


def test_key_builders():
    assert make_chain_key("SPY", "2024-01-19") == "chain:SPY:2024-01-19"
    assert make_expiries_key("spy") == "expiries:SPY"
    assert make_rate_key() == "rate:risk_free"


def test_set_get_round_trip(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    c.set("k", {"a": 1, "b": [1, 2, 3]}, ttl_seconds=60)
    assert c.get("k") == {"a": 1, "b": [1, 2, 3]}
    c.close()


def test_get_missing_returns_none(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    assert c.get("does-not-exist") is None
    c.close()


def test_expired_entry_returns_none(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    c.set("k", "v", ttl_seconds=1)
    # force expiry by rewriting expires_at to the past
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "c.sqlite"))
    conn.execute("UPDATE cache SET expires_at = 0 WHERE key = ?", ("k",))
    conn.commit()
    conn.close()
    assert c.get("k") is None


def test_purge_expired_removes_rows(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    c.set("keep", "v", ttl_seconds=3600)
    c.set("gone", "v", ttl_seconds=1)
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "c.sqlite"))
    conn.execute("UPDATE cache SET expires_at = 0 WHERE key = ?", ("gone",))
    conn.commit()
    conn.close()
    c.purge_expired()
    assert c.get("keep") == "v"
    assert c.get("gone") is None


def test_corrupt_db_is_graceful_no_op(tmp_path):
    db = tmp_path / "corrupt.sqlite"
    # write garbage bytes that are not a valid SQLite database
    with open(db, "wb") as f:
        f.write(b"not a sqlite database\x00\x01garbage")

    # Cache.__init__ should swallow the corruption and degrade silently.
    c = Cache(db)
    # get must not raise and must return None
    assert c.get("anything") is None
    # set must not raise and must be a no-op
    c.set("k", "v", ttl_seconds=60)
    assert c.get("k") is None
    # purge must not raise
    c.purge_expired()
    c.close()


def test_negative_ttl_is_noop(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    c.set("k", "v", ttl_seconds=-5)
    assert c.get("k") is None
    c.close()
