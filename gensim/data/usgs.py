"""USGS daily mean discharge (parameter 00060, statistic 00003 = daily mean), cached to disk.

Primary: the OGC API at api.waterdata.usgs.gov (v1; follows `next` links).
Fallback: the legacy NWIS daily-values service (waterservices.usgs.gov/nwis/dv), being retired.

Daily values are calendar dates at the gauge (no time-of-day), so they are kept as dates.
Provisional values are revised by USGS; `refresh=True` refetches the whole record.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

from gensim.config import DATA_CACHE, contact_email
from gensim.data.http import FetchError, http_get

OGC_DAILY = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/items"
NWIS_DV = "https://waterservices.usgs.gov/nwis/dv/"
DISCHARGE = "00060"
DAILY_MEAN = "00003"
RECORD_START = "1900-01-01"


def _headers() -> dict:
    try:
        return {"User-Agent": f"gen-sim/0.1 ({contact_email()})"}
    except Exception:
        return {"User-Agent": "gen-sim/0.1"}


def cache_path(site: str) -> Path:
    return DATA_CACHE / "usgs" / f"USGS-{site}_{DISCHARGE}_daily.csv"


def _fetch_ogc(site: str, start: str, end: str, get=http_get) -> pd.DataFrame:
    params = {
        "monitoring_location_id": f"USGS-{site}", "parameter_code": DISCHARGE, "statistic_id": DAILY_MEAN,
        "time": f"{start}/{end}", "limit": "10000", "f": "json",   # no sortby: it disables paging
    }
    url, rows = OGC_DAILY, []
    while url:
        j = get(url, params=params, headers=_headers(), timeout=120).json()
        for feat in j.get("features", []):
            p = feat["properties"]
            rows.append({"date": p["time"][:10], "q_cfs": p.get("value"),
                         "approval": p.get("approval_status"), "qualifier": p.get("qualifier")})
        url = next((l["href"] for l in j.get("links", []) if l.get("rel") == "next"), None)
        params = None  # the next link carries the query
    return pd.DataFrame(rows, columns=["date", "q_cfs", "approval", "qualifier"])


def _fetch_nwis(site: str, start: str, end: str, get=http_get) -> pd.DataFrame:
    params = {"format": "json", "sites": site, "parameterCd": DISCHARGE, "statCd": DAILY_MEAN,
              "startDT": start, "endDT": end, "siteStatus": "all"}
    j = get(NWIS_DV, params=params, headers=_headers(), timeout=120).json()
    rows = []
    for ts in j["value"]["timeSeries"]:
        for v in ts["values"][0]["value"]:
            quals = v.get("qualifiers") or []
            rows.append({"date": v["dateTime"][:10], "q_cfs": v["value"],
                         "approval": "Provisional" if "P" in quals else "Approved", "qualifier": ",".join(quals)})
    return pd.DataFrame(rows, columns=["date", "q_cfs", "approval", "qualifier"])


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["q_cfs"] = pd.to_numeric(df["q_cfs"], errors="coerce")
    # USGS uses large negative sentinels (e.g. -999999) for missing/ice values
    df.loc[df["q_cfs"] < 0, "q_cfs"] = float("nan")
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def daily_discharge(site: str, *, refresh: bool = False, start: str = RECORD_START,
                    end: str | None = None, get=http_get) -> pd.DataFrame:
    """Columns: date (YYYY-MM-DD), q_cfs, approval, qualifier. Uses the on-disk cache unless refresh."""
    path = cache_path(site)
    if path.exists() and not refresh:
        return pd.read_csv(path, dtype={"date": str})
    end = end or date.today().isoformat()
    try:
        df, source = _fetch_ogc(site, start, end, get), "OGC API"
    except FetchError as e:
        print(f"⚠️ USGS OGC API failed ({e}); falling back to legacy NWIS dv")
        df, source = _fetch_nwis(site, start, end, get), "legacy NWIS"
    if df.empty:
        raise FetchError(f"USGS returned no daily discharge for site {site}")
    df = _clean(df)
    os.makedirs(path.parent, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"✅ USGS {site}: {len(df)} days {df['date'].iloc[0]} → {df['date'].iloc[-1]} via {source}; cached {path.name}")
    return df
