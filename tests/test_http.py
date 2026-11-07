"""Ported Historical network code: retry/backoff, no retry on 4xx, key redaction, EIA pagination."""
import pytest
import requests

from gensim.data import http
from gensim.data.http import FetchError, eia_v2_data, http_get


class _Resp:
    def __init__(self, status, payload=None, url="https://api.eia.gov/v2/x/data/?api_key=SECRETKEY123&frequency=hourly"):
        self.status_code, self._payload, self.url, self.text = status, payload or {}, url, "body"

    def json(self):
        return self._payload


def test_retries_then_succeeds(monkeypatch):
    seq = [_Resp(503), requests.ConnectionError("boom"), _Resp(200, {"ok": 1})]
    def fake_get(*a, **k):
        r = seq.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(http.requests, "get", fake_get)
    sleeps = []
    assert http_get("u", sleep=sleeps.append).json() == {"ok": 1}
    assert len(sleeps) == 2


def test_client_error_fails_fast_and_redacts(monkeypatch):
    calls = []
    monkeypatch.setattr(http.requests, "get", lambda *a, **k: calls.append(1) or _Resp(403))
    with pytest.raises(FetchError) as ei:
        http_get("u", sleep=lambda s: None)
    assert len(calls) == 1
    assert "SECRETKEY123" not in str(ei.value) and "api_key=***" in str(ei.value)


def test_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(http.requests, "get", lambda *a, **k: _Resp(500))
    with pytest.raises(FetchError, match="failed after 3 attempts"):
        http_get("u", retries=3, sleep=lambda s: None)


def test_eia_pagination(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "dummy")
    monkeypatch.setattr(http, "EIA_PAGE", 2)
    pages = {"0": [{"period": 1}, {"period": 2}], "2": [{"period": 3}, {"period": 4}], "4": [{"period": 5}]}
    seen = []
    def fake_get(url, params):
        off = dict(params)["offset"]; seen.append(off)
        return _Resp(200, {"response": {"total": "5", "data": pages[off]}})
    rows = eia_v2_data("electricity/facility-fuel", frequency="monthly", facets={"plantCode": [10798]}, session_get=fake_get)
    assert [r["period"] for r in rows] == [1, 2, 3, 4, 5] and seen == ["0", "2", "4"]


def test_eia_error_payload_raises(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "dummy")
    with pytest.raises(FetchError, match="EIA error"):
        eia_v2_data("x", frequency="monthly", session_get=lambda url, params: _Resp(200, {"error": "bad facet"}))
