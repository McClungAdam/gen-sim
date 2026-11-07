"""USGS + EIA-923 fetchers: parsing, paging, fallback, caching. Offline (fake responses)."""
import pandas as pd
import pytest

import gensim.config
from gensim.data import eia923, usgs
from gensim.data.http import FetchError


class _R:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(usgs, "DATA_CACHE", tmp_path)
    monkeypatch.setattr(eia923, "DATA_CACHE", tmp_path)
    return tmp_path


def _feat(d, v, appr="Approved"):
    return {"properties": {"time": d, "value": v, "approval_status": appr, "qualifier": None}}


def test_usgs_ogc_follows_next_links_and_cleans():
    pages = [
        {"features": [_feat("1930-01-02", "500"), _feat("1930-01-01", "-999999")],
         "links": [{"rel": "next", "href": "https://next/page2"}]},
        {"features": [_feat("1930-01-03", "450", "Provisional")], "links": []},
    ]
    seen = []
    def get(url, params=None, **k):
        seen.append((url, params is None)); return _R(pages.pop(0))
    df = usgs.daily_discharge("03164000", get=get, end="1930-01-03")
    assert df["date"].tolist() == ["1930-01-01", "1930-01-02", "1930-01-03"]   # sorted locally
    assert pd.isna(df["q_cfs"].iloc[0])                                          # sentinel -> NaN
    assert seen[1] == ("https://next/page2", True)                               # next link carries query
    assert usgs.cache_path("03164000").exists()


def test_usgs_falls_back_to_nwis_and_uses_cache():
    nwis = {"value": {"timeSeries": [{"values": [{"value": [
        {"dateTime": "1930-01-01T00:00:00.000", "value": "600", "qualifiers": ["A"]},
        {"dateTime": "1930-01-02T00:00:00.000", "value": "610", "qualifiers": ["P"]}]}]}]}}
    def get(url, params=None, **k):
        if "ogcapi" in url:
            raise FetchError("HTTP 503")
        return _R(nwis)
    df = usgs.daily_discharge("03164000", get=get, end="1930-01-02")
    assert df["q_cfs"].tolist() == [600.0, 610.0] and df["approval"].tolist() == ["Approved", "Provisional"]
    again = usgs.daily_discharge("03164000", get=lambda *a, **k: pytest.fail("should use cache"))
    assert again["q_cfs"].tolist() == [600.0, 610.0]


def test_eia923_plant_total_and_units():
    rows = [{"period": "2003-02", "generation": "2500.5", "generation-units": "megawatthours"},
            {"period": "2003-01", "generation": "3000", "generation-units": "megawatthours"}]
    calls = []
    def fetch(route, **k):
        calls.append((route, k["facets"])); return rows
    df = eia923.monthly_generation(10798, fetch=fetch)
    assert df.to_dict("records") == [{"month": "2003-01", "net_generation_mwh": 3000.0},
                                     {"month": "2003-02", "net_generation_mwh": 2500.5}]
    assert calls[0][1]["fuel2002"] == ["ALL"] and calls[0][1]["primeMover"] == ["ALL"]


def test_eia923_rejects_unexpected_units():
    rows = [{"period": "2003-01", "generation": "3", "generation-units": "thousand megawatthours"}]
    with pytest.raises(ValueError, match="units"):
        eia923.monthly_generation(1, fetch=lambda *a, **k: rows)


def test_capacity_latest_month_only():
    rows = [{"period": "2026-07", "generatorid": "GEN1", "nameplate-capacity-mw": "2", "net-summer-capacity-mw": "1.9",
             "net-winter-capacity-mw": "1.9", "status": "OP", "entityName": "X"},
            {"period": "2026-08", "generatorid": "GEN1", "nameplate-capacity-mw": "2", "net-summer-capacity-mw": "2",
             "net-winter-capacity-mw": "2", "status": "OP", "entityName": "X"}]
    df = eia923.generator_capacity(10798, fetch=lambda *a, **k: rows)
    assert len(df) == 1 and df["summer_mw"].iloc[0] == 2.0
