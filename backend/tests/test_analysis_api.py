"""Offline tests for the /analysis endpoint (stubbed yfinance, no network)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.data.cache import Cache
from app.data.models import DataError

from tests.test_mispricing import make_synthetic_chain

_TODAY = datetime.now(timezone.utc).date()
_DTE = 30
_EXPIRY = (_TODAY + timedelta(days=_DTE)).isoformat()


class StubYFinance:
    def __init__(self, chain=None, error=None):
        self.chain = chain
        self.error = error
        self.calls = 0

    async def get_chain(self, symbol, expiry):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.chain


@pytest.fixture
def client_and_stub(tmp_path, monkeypatch):
    monkeypatch.setattr("app.data.cache.DEFAULT_DB_PATH", tmp_path / "cache.sqlite")
    from app.main import create_app

    app = create_app()
    stub = StubYFinance(chain=make_synthetic_chain(asof=_TODAY, dte_days=_DTE))
    with TestClient(app) as client:
        app.state.yfinance = stub
        app.state.fred = None
        app.state.cache = Cache(db_path=tmp_path / "analysis-cache.sqlite")
        yield client, stub


def test_analysis_ok_shape_and_fallback_rate(client_and_stub):
    client, _ = client_and_stub
    resp = client.get("/analysis/SYN", params={"expiry": _EXPIRY})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "SYN"
    assert body["rate_source"] == "fallback"
    assert body["forward_source"] == "parity"
    assert body["fit"]["fitted"] is True
    assert body["flagged_count"] == 0
    assert len(body["contracts"]) == 50  # 25 strikes x 2 sides
    assert len(body["parity"]) == 25
    assert body["params"]["z_threshold"] == 2.0


def test_analysis_malformed_expiry(client_and_stub):
    client, _ = client_and_stub
    resp = client.get("/analysis/SYN", params={"expiry": "not-a-date"})
    assert resp.status_code == 400


def test_analysis_past_expiry(client_and_stub):
    client, _ = client_and_stub
    past = (_TODAY - timedelta(days=7)).isoformat()
    resp = client.get("/analysis/SYN", params={"expiry": past})
    assert resp.status_code == 400


def test_analysis_unknown_symbol_404(client_and_stub):
    client, stub = client_and_stub
    stub.error = DataError("Symbol NOPE not found")
    resp = client.get("/analysis/NOPE", params={"expiry": _EXPIRY})
    assert resp.status_code == 404


def test_analysis_upstream_error_502(client_and_stub):
    client, stub = client_and_stub
    stub.error = RuntimeError("yahoo went away")
    resp = client.get("/analysis/SYN", params={"expiry": _EXPIRY})
    assert resp.status_code == 502


def test_analysis_repeat_request_served_from_cache(client_and_stub):
    client, _ = client_and_stub
    first = client.get("/analysis/SYN", params={"expiry": _EXPIRY})
    second = client.get("/analysis/SYN", params={"expiry": _EXPIRY})
    assert first.status_code == second.status_code == 200
    # The chain snapshot is unchanged, so the second response must be the
    # cached analysis: identical computed_at, not a recomputation.
    assert first.json()["computed_at"] == second.json()["computed_at"]


def test_analysis_param_change_bypasses_cache(client_and_stub):
    client, _ = client_and_stub
    default = client.get("/analysis/SYN", params={"expiry": _EXPIRY})
    changed = client.get(
        "/analysis/SYN", params={"expiry": _EXPIRY, "z_threshold": 3.0}
    )
    assert default.status_code == changed.status_code == 200
    # Must be a fresh computation with the new params, not the cached
    # default-params analysis (whose params block would say 2.0).
    assert changed.json()["params"]["z_threshold"] == 3.0
    assert changed.json()["computed_at"] != default.json()["computed_at"]
    # And the changed-params result gets its own cache entry.
    repeat = client.get(
        "/analysis/SYN", params={"expiry": _EXPIRY, "z_threshold": 3.0}
    )
    assert repeat.status_code == 200
    assert repeat.json()["computed_at"] == changed.json()["computed_at"]


def test_analysis_param_validation(client_and_stub):
    client, _ = client_and_stub
    resp = client.get(
        "/analysis/SYN", params={"expiry": _EXPIRY, "z_threshold": 0.1}
    )
    assert resp.status_code == 422
