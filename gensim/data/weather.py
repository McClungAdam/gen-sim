"""NWS (api.weather.gov) weather: observed history, hourly forecast, and the merged series.

Ported from legacy get_weather_observed.py / get_weather_forecast.py / merge_weather_inputs.py;
behavior unchanged. Out of scope for Phase 1 beyond keeping it working.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from gensim.config import Paths, user_agent

STATION = "KINT"            # Winston-Salem Airport
MAX_LOOKBACK_HRS = 168      # max NOAA window (~7 days)
FORECAST_GRID = ("RAH", 76, 45)   # Winston-Salem grid point


def fetch_observed(paths: Paths) -> pd.DataFrame:
    archive = paths.weather_observed
    headers = {"User-Agent": user_agent()}

    # 1) Determine time range to fetch
    now = datetime.now(timezone.utc)
    old = None
    if os.path.exists(archive):
        old = pd.read_csv(archive, parse_dates=["timestamp"])
        old["timestamp"] = pd.to_datetime(old["timestamp"], utc=True)
        last_ts = old["timestamp"].max()
        start = last_ts + timedelta(hours=1)
        # NOAA only serves the last ~7 days, so bound start to now - MAX_LOOKBACK_HRS
        cutoff = now - timedelta(hours=MAX_LOOKBACK_HRS)
        if start < cutoff:
            start = cutoff
    else:
        start = now - timedelta(hours=MAX_LOOKBACK_HRS)

    # 2) Build URL (strip microseconds, force Z)
    start_str = start.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = now.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"https://api.weather.gov/stations/{STATION}/observations"
        f"?start={start_str}&end={end_str}"
    )

    # 3) Fetch & parse
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    records = []
    for feat in r.json()["features"]:
        p = feat["properties"]
        ts = pd.to_datetime(p["timestamp"], utc=True)
        temp = p["temperature"]["value"]
        records.append({
            "timestamp": ts,
            "temp_f": temp * 9 / 5 + 32 if temp is not None else None,
            "condition": p["textDescription"],
            "windSpeed": p["windSpeed"]["value"],
            "temperatureUnit": "F",
        })
    new = pd.DataFrame(records)

    # 4) Append to archive, dedupe, sort
    df = pd.concat([old, new], ignore_index=True) if old is not None else new
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    # 5) Save
    df.to_csv(archive, index=False)
    print(f"✅ Appended {len(new)} rows → {archive.name} now has {len(df)} rows")
    print(f"    Range: {df['timestamp'].min()} → {df['timestamp'].max()}")
    return df


def fetch_forecast(paths: Paths) -> pd.DataFrame:
    grid_id, grid_x, grid_y = FORECAST_GRID
    url = f"https://api.weather.gov/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast/hourly"
    headers = {"User-Agent": user_agent()}

    response = requests.get(url, headers=headers)
    data = response.json()

    periods = data["properties"]["periods"]
    df = pd.DataFrame(periods)
    df["timestamp"] = pd.to_datetime(df["startTime"])
    df["temp_f"] = df["temperature"]
    df["condition"] = df["shortForecast"]
    df["windSpeed"] = df["windSpeed"]
    df["temperatureUnit"] = df["temperatureUnit"]
    df = df[["timestamp", "temp_f", "temperatureUnit", "windSpeed", "condition"]]

    df.to_csv(paths.weather_forecast, index=False)  # overwrite
    print(f"✅ Saved {paths.weather_forecast.name} with {len(df)} hourly forecast rows")
    return df


def merge_weather(paths: Paths, now: datetime | None = None) -> pd.DataFrame:
    """Observed (<= now) + forecast (> now) -> merged_weather.csv. `now` is injectable for tests."""
    observed = pd.read_csv(paths.weather_observed, parse_dates=["timestamp"])
    forecast = pd.read_csv(paths.weather_forecast, parse_dates=["timestamp"])

    now = now if now is not None else datetime.now(timezone.utc)
    observed = observed[observed["timestamp"] <= now]
    forecast = forecast[forecast["timestamp"] > now]

    merged = pd.concat([observed, forecast], ignore_index=True)
    merged = merged.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

    # Normalize timestamps: strip timezone (KEEP native cadence; do NOT round to hour)
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True).dt.tz_localize(None)

    merged.to_csv(paths.merged_weather, index=False)
    print(f"✅ Saved {paths.merged_weather.name} with {len(merged)} rows "
          f"(from {merged['timestamp'].min()} to {merged['timestamp'].max()})")
    return merged
