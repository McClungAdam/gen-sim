"""EIA Open Data v2 fetchers: Duke BA hourly demand (EIA-930) and Henry Hub daily spot.

All requests go through gensim.data.http (retry/backoff, pagination, key redaction).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from gensim.config import Paths
from gensim.data.http import eia_v2_data

# ---------------------------------------------------------------- demand (EIA-930)
DUK_ID = "DUK"            # Duke Energy's balancing authority ID
DEMAND_DAYS_BACK = 60


def fetch_duk_demand(paths: Paths) -> pd.DataFrame:
    start = (datetime.now(timezone.utc) - timedelta(days=DEMAND_DAYS_BACK)).strftime("%Y-%m-%dT00")
    rows = eia_v2_data("electricity/rto/region-data", frequency="hourly",
                       facets={"respondent": [DUK_ID], "type": ["D"]}, start=start)
    if not rows:
        raise RuntimeError("EIA-930 returned no DUK demand rows")
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["period"], utc=True)  # EIA-930 hourly periods are UTC
    df["demand_mw"] = pd.to_numeric(df["value"], errors="coerce")
    df = df[["timestamp", "demand_mw"]].sort_values("timestamp").drop_duplicates("timestamp")

    df.to_csv(paths.demand, index=False)
    print(f"✅ Saved {paths.demand.name} with {len(df)} rows from {df['timestamp'].min()} to {df['timestamp'].max()}")
    return df


# ---------------------------------------------------------------- Henry Hub daily
HENRY_HUB_SERIES = "RNGWHHD"   # Henry Hub natural gas spot price, $/MMBtu, daily
GAS_HISTORY_DAYS = 365


def fetch_henry_hub(paths: Paths) -> pd.DataFrame:
    start = (datetime.now(timezone.utc) - timedelta(days=GAS_HISTORY_DAYS)).strftime("%Y-%m-%d")
    rows = eia_v2_data("natural-gas/pri/fut", frequency="daily",
                       facets={"series": [HENRY_HUB_SERIES]}, start=start)
    if not rows:
        raise RuntimeError("EIA returned no Henry Hub rows")
    new_df = pd.DataFrame(rows)[["period", "value"]].rename(columns={"period": "date", "value": "gas_price"})
    new_df["date"] = pd.to_datetime(new_df["date"])
    new_df["gas_price"] = pd.to_numeric(new_df["gas_price"], errors="coerce")

    archive = paths.gas
    if os.path.exists(archive):
        old_df = pd.read_csv(archive, parse_dates=["date"]).rename(columns={"price": "gas_price"})
        df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        df = new_df

    df = df.dropna(subset=["date", "gas_price"]).drop_duplicates(subset="date", keep="last").sort_values("date")
    df = df[df["date"] >= datetime.now() - timedelta(days=GAS_HISTORY_DAYS)]
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")    # a trading day, not an instant

    df.to_csv(archive, index=False)
    print(f"✅ Saved {archive.name} with {len(df)} rows (through {df['date'].max()})")
    return df
