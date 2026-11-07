"""EIA Open Data v2 fetchers: Duke BA hourly demand (EIA-930) and Henry Hub daily spot.

Ported from legacy get_demand.py / get_gas_prices.py; behavior unchanged.
"""
from __future__ import annotations

import datetime as _dt
import os
from datetime import datetime, timedelta

import pandas as pd
import requests

from gensim.config import Paths, eia_api_key

# ---------------------------------------------------------------- demand (EIA-930)
DUK_ID = "DUK"            # Duke Energy's balancing authority ID
DEMAND_DAYS_BACK = 60


def fetch_duk_demand(paths: Paths) -> pd.DataFrame:
    api_key = eia_api_key()
    today = _dt.datetime.now()
    start_date = (today - _dt.timedelta(days=DEMAND_DAYS_BACK)).strftime("%Y-%m-%d")
    url = (
        f"https://api.eia.gov/v2/electricity/rto/region-data/data/"
        f"?api_key={api_key}"
        f"&frequency=hourly"
        f"&data[0]=value"
        f"&facets[respondent][]={DUK_ID}"
        f"&facets[type][]=D"
        f"&start={start_date}"
    )
    r = requests.get(url)
    j = r.json()
    data = j["response"]["data"]

    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["period"], utc=True)  # EIA-930 hourly periods are UTC
    df = df[["timestamp", "value"]].sort_values("timestamp")

    df.to_csv(paths.demand, index=False)
    print(f"✅ Saved {paths.demand.name} with {len(df)} rows from {df['timestamp'].min()} to {df['timestamp'].max()}")
    return df


# ---------------------------------------------------------------- Henry Hub daily
HENRY_HUB_SERIES = "NG.RNGWHHD.D"   # Henry Hub daily spot price
GAS_HISTORY_DAYS = 365


def fetch_henry_hub(paths: Paths) -> pd.DataFrame | None:
    api_key = eia_api_key()
    url = f"https://api.eia.gov/v2/seriesid/{HENRY_HUB_SERIES}?api_key={api_key}"
    archive = paths.gas

    r = requests.get(url)
    j = r.json()

    if "response" in j and "data" in j["response"]:
        new_df = pd.DataFrame(j["response"]["data"])
        cols = [c for c in ["period", "value"] if c in new_df.columns]
        new_df = new_df[cols].rename(columns={"period": "date", "value": "price"})
        new_df["date"] = pd.to_datetime(new_df["date"])

        if os.path.exists(archive):
            old_df = pd.read_csv(archive, parse_dates=["date"])
            df = pd.concat([old_df, new_df], ignore_index=True)
        else:
            df = new_df

        df = df.drop_duplicates(subset="date")
        df = df.sort_values("date")
        df = df[df["date"] >= datetime.now() - timedelta(days=GAS_HISTORY_DAYS)]

        df.to_csv(archive, index=False)
        print("✅ Saved", archive.name, "with", len(df), "rows (through", df["date"].max().date(), ")")
        return df

    # Never print the request URL: it contains the API key.
    print("❌ Unexpected response shape")
    print("Status:", r.status_code)
    print("Body:", r.text)
    return None
