"""Offline tests for the /alerts endpoints (stubbed scanner, no network)."""
import time

import pytest
from fastapi.testclient import TestClient

from app.analysis import Scanner, ScannerConfig

from tests.test_scanner import StubYFinance, _rich_chain


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("app.data.cache.DEFAULT_DB_PATH", tmp_path / "cache.sqlite")
    monkeypatch.delenv("OFV_SCANNER_ENABLED", raising=False)
    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        # Polling for background-sweep completion would trip the per-IP limit.
        app.state.limiter.enabled = False
        yield c, app


def _poll_alerts(c, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = c.get("/alerts").json()
        if predicate(body):
            return body
        time.sleep(0.05)
    raise AssertionError("alerts condition not met within timeout")


def test_alerts_disabled_returns_empty_feed(client):
    c, app = client
    assert app.state.scanner is None
    resp = c.get("/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"]["enabled"] is False
    assert body["active"] == [] and body["pending"] == []


def test_manual_scan_disabled_503(client):
    c, _ = client
    assert c.post("/alerts/scan").status_code == 503


def test_manual_scan_runs_sweep_and_persists_alerts(client):
    c, app = client
    config = ScannerConfig(
        watchlist=("SYN",), persistence_scans=2, min_dte=1, max_dte=90,
        throttle_seconds=0.0,
    )
    app.state.scanner = Scanner(
        yfinance=StubYFinance(_rich_chain()), cache=None, fred=None, config=config
    )

    # Fire-and-forget: 202 immediately, sweep completes in the background.
    first = c.post("/alerts/scan")
    assert first.status_code == 202
    assert first.json()["status"]["enabled"] is True
    body = _poll_alerts(
        c, lambda b: len(b["pending"]) == 1 and not b["status"]["scanning"]
    )
    assert body["active"] == []

    second = c.post("/alerts/scan")
    assert second.status_code == 202
    body = _poll_alerts(
        c, lambda b: len(b["active"]) == 1 and not b["status"]["scanning"]
    )
    assert body["pending"] == []
    rec = body["active"][0]
    assert rec["symbol"] == "SYN"
    assert rec["verdict"] == "rich"
    assert rec["streak"] == 2
