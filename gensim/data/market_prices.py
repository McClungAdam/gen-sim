"""Legacy EIA "market price" fetcher. Ported from get_market_prices.py; behavior unchanged.

KNOWN DEFECTS (fixed in follow-up commits, pinned by tests/golden):
  #1  _try_eia_v2_seriesid maps BA codes to EIA-930 DEMAND series, and _normalize_prices_df
      divides values with median > 1000 by 100, producing fake $/MWh.
  #2  the electricity/wholesale-prices route is not believed to exist.
  #4  timestamps are labeled America/New_York but are UTC.
Do NOT run fetch_market_prices against live EIA until #1 is fixed.
"""
from __future__ import annotations

import io
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from gensim.config import Paths, eia_api_key, redact


# ----- Helper: normalize and save -----
def normalize_prices_df(df: pd.DataFrame) -> pd.DataFrame:
    # Accept flexible inputs, but enforce timestamp + price_mwh and naive local (America/New_York)
    if "timestamp" not in df.columns and "period" in df.columns:
        df = df.rename(columns={"period": "timestamp"})
    if "price_mwh" not in df.columns and "value" in df.columns:
        df = df.rename(columns={"value": "price_mwh"})
    if not {"timestamp", "price_mwh"}.issubset(df.columns):
        raise ValueError("Input must contain 'timestamp' and 'price_mwh' (or mappable columns).")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    # If tz-aware, convert to America/New_York and drop tz; if tz-naive, localize as NY then drop tz
    if isinstance(df["timestamp"].dtype, pd.DatetimeTZDtype):
        df["timestamp"] = df["timestamp"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    else:
        df["timestamp"] = df["timestamp"].dt.tz_localize("America/New_York", nonexistent="shift_forward", ambiguous="NaT").dt.tz_localize(None)
    # price hygiene
    df["price_mwh"] = pd.to_numeric(df["price_mwh"], errors="coerce")
    med = df["price_mwh"].median()
    if pd.notna(med) and med > 1000:
        df["price_mwh"] = df["price_mwh"] / 100.0  # correct cents/MWh feeds
    out = df[["timestamp", "price_mwh"]].dropna(subset=["timestamp"]).sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    return out


class _Fetcher:
    """Holds the per-run settings the legacy script kept as module globals."""

    def __init__(self, cfg: dict, paths: Paths):
        market = cfg.get("market", {})
        self.ba = market.get("ba", "DUK")                # Balancing Authority code (e.g., DUK, PJM, TVA)
        self.series = market.get("price_series", "DA")   # "DA" or "RT"
        self.api_key = eia_api_key()
        self.out = paths.market_price

    def _save(self, df: pd.DataFrame, label: str):
        out = normalize_prices_df(df)
        out.to_csv(self.out, index=False)
        print(f"✅ Saved {self.out.name} with {len(out)} rows for BA={self.ba}, Series={self.series} via {label}")
        return out

    @staticmethod
    def _aggregate_to_15min(df_5min: pd.DataFrame) -> pd.DataFrame:
        df_5min = normalize_prices_df(df_5min)
        return (
            df_5min.set_index("timestamp")
                   .resample("15min")["price_mwh"]
                   .mean()
                   .to_frame()
                   .reset_index()
        )

    def try_eia_v2_hourly(self):
        start_date = (datetime.now(timezone.utc) - timedelta(days=120)).strftime("%Y-%m-%d")
        url = (
            "https://api.eia.gov/v2/electricity/wholesale-prices/data/"
            f"?api_key={self.api_key}"
            f"&frequency=hourly"
            f"&data[0]=value"
            f"&facets[respondent][]={self.ba}"
            f"&start={start_date}"
        )
        if self.series in ("DA", "RT"):
            url += f"&facets[market][]={self.series}"
        r = requests.get(url, timeout=45)
        r.raise_for_status()
        j = r.json()
        data = j.get("response", {}).get("data", [])
        rows = []
        for item in data:
            ts = item.get("period")
            val = item.get("value")
            if ts is None or val is None:
                continue
            rows.append({"timestamp": ts, "price_mwh": float(val)})
        if not rows:
            raise RuntimeError("EIA v2 hourly returned 0 rows")
        return self._save(pd.DataFrame(rows), "EIA v2 hourly")

    def try_eia_v2_seriesid(self):
        series_ids = {
            ("DUK", "DA"): "EBA.DUK-ALL.D.H",
            ("DUK", "RT"): "EBA.DUK-ALL.H.H",
            ("PJM", "DA"): "EBA.PJM-ALL.D.H",
            ("PJM", "RT"): "EBA.PJM-ALL.H.H",
            ("TVA", "DA"): "EBA.TVA-ALL.D.H",
            ("TVA", "RT"): "EBA.TVA-ALL.H.H",
        }
        sid = series_ids.get((self.ba, self.series))
        if not sid:
            raise RuntimeError(f"No v1 series mapping for BA={self.ba}, Series={self.series}")
        url = f"https://api.eia.gov/v2/seriesid/{sid}?api_key={self.api_key}"
        r = requests.get(url, timeout=45)
        r.raise_for_status()
        jj = r.json()
        data = jj.get("response", {}).get("data", [])
        rows = []
        for item in data:
            ts = item.get("period")
            val = item.get("value")
            if ts is None or val is None:
                continue
            rows.append({"timestamp": ts, "price_mwh": float(val)})
        if not rows:
            raise RuntimeError("EIA v2 seriesid returned 0 rows")
        return self._save(pd.DataFrame(rows), "EIA v2 seriesid")

    def try_eia_v2_5min_pjm(self):
        start_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        url = (
            "https://api.eia.gov/v2/electricity/wholesale-prices/data/"
            f"?api_key={self.api_key}"
            f"&frequency=5min"
            f"&data[0]=value"
            f"&facets[respondent][]=PJM"
            f"&facets[market][]=RT"
            f"&start={start_date}"
        )
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        j = r.json()
        data = j.get("response", {}).get("data", [])
        if not data:
            raise RuntimeError("EIA v2 5min returned 0 rows")
        rows = [{"timestamp": d["period"], "price_mwh": float(d["value"])} for d in data if "period" in d and "value" in d]
        df5 = pd.DataFrame(rows)
        return self._aggregate_to_15min(df5)

    @staticmethod
    def try_env_csv():
        url = os.getenv("PJM_5MIN_URL", "").strip()
        fpath = os.getenv("PJM_5MIN_FILE", "").strip()
        if url:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text))
            cols_lower = {c.lower(): c for c in df.columns}
            ts_col = cols_lower.get("timestamp") or cols_lower.get("datetime") or cols_lower.get("datetime_utc") or cols_lower.get("date_utc")
            price_col = cols_lower.get("price_mwh") or cols_lower.get("lmp") or cols_lower.get("rt_lmp") or cols_lower.get("price")
            if not (ts_col and price_col):
                raise RuntimeError("Provided CSV lacks recognizable timestamp/price columns")
            df = df.rename(columns={ts_col: "timestamp", price_col: "price_mwh"})
            return df
        if fpath and os.path.exists(fpath):
            df = pd.read_csv(fpath)
            if not {"timestamp", "price_mwh"}.issubset(df.columns):
                raise RuntimeError("Local CSV must contain 'timestamp' and 'price_mwh' columns")
            return df
        raise RuntimeError("No PJM_5MIN_URL or PJM_5MIN_FILE provided")


def fetch_market_prices(cfg: dict, paths: Paths):
    f = _Fetcher(cfg, paths)
    enable_5min = os.getenv("ENABLE_PJM_5MIN", "0") == "1"
    if f.ba.upper() == "PJM" and f.series.upper() == "RT" and enable_5min:
        print("ℹ️ ENABLE_PJM_5MIN=1 and BA=PJM RT detected; attempting 5‑minute prices...")
        try:
            df15 = f.try_eia_v2_5min_pjm()
            return f._save(df15, "EIA v2 5min (aggregated to 15min)")
        except Exception as e:
            print(f"⚠️ EIA 5‑minute path failed: {redact(e)}")
        try:
            df5 = f.try_env_csv()
            df15 = f._aggregate_to_15min(df5)
            return f._save(df15, "Custom PJM 5min (aggregated to 15min)")
        except Exception as e:
            print(f"⚠️ Custom 5‑minute CSV path failed: {redact(e)}")
        print("ℹ️ Falling back to hourly EIA APIs...")

    # Default hourly flow (any BA/series)
    try:
        return f.try_eia_v2_hourly()
    except Exception as e:
        print(f"⚠️ Hourly v2 failed: {redact(e)}. Trying v2 seriesid...")
        return f.try_eia_v2_seriesid()
