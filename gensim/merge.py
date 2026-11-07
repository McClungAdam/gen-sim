"""Build the merged hourly/15-min input timeline. Ported from legacy merge_inputs.py; behavior unchanged.

Timestamps: tz-aware UTC throughout (gensim.timeutil). Source rules:
  demand (EIA-930)           naive = UTC (documented by EIA)
  merged_weather, prices     written by this pipeline: must carry offsets, naive raises
  gas (daily)                calendar day -> start of that day in market time
  site_load / avoided_cost   user files: naive = market time
  config/CSV windows, `now`  human input: naive = market time

Inputs (defect #6): every source has standard column names (SCHEMAS); legacy names are mapped
explicitly, missing required columns/files raise MissingInput, nothing is silently dropped.

Gas (defect #5): each daily print covers its whole local day and carries over non-trading days
(weekends/holidays) up to GAS_MAX_CARRY; beyond that the hour is left NaN and the simulator refuses
to run rather than inventing a fuel price.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from gensim.config import Paths
from gensim.timeutil import dates_to_utc_day_start, market_tz, now_utc, series_to_utc
from gensim.windows import flag_windows as _flag_windows

LOOKBACK_DAYS = 45
LOOKAHEAD_DAYS = 14
GAS_MAX_CARRY = timedelta(days=4)   # Friday print through a Monday holiday


def _min_step_seconds(ts):
    ser = pd.to_datetime(ts).sort_values().dropna()
    diffs = ser.diff().dt.total_seconds()
    diffs = diffs[diffs > 0]
    return float(diffs.min()) if not diffs.empty else float("inf")


def _target_freq(steps):
    return "15min" if any(s < 3600 for s in steps if s != float("inf")) else "h"


def _load_windows_csv(path):
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path)
        out = []
        for _, r in df.iterrows():
            out.append({"start": r.get("start"), "end": r.get("end"), "note": r.get("note", "")})
        return out
    except Exception:
        return []


def _resample_ffill(df, freq):
    if df is None or df.empty:
        return None
    df = df.sort_values("timestamp").set_index("timestamp").resample(freq).ffill()
    return df.reset_index()


def _gas_on_timeline(gas: pd.DataFrame, timeline_ts: pd.Series) -> pd.Series:
    """Daily prints (timestamp = local day start, UTC) -> price for every timeline step."""
    g = gas.dropna(subset=["timestamp"]).sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    g = g.set_index("timestamp")["gas_price"].astype(float)
    grid = g.index.union(pd.DatetimeIndex(timeline_ts))
    price = g.reindex(grid).ffill()
    print_time = pd.Series(g.index, index=g.index).reindex(grid).ffill()
    stale = (grid.to_series() - print_time) >= GAS_MAX_CARRY
    price[stale.to_numpy()] = np.nan
    return pd.Series(price.reindex(pd.DatetimeIndex(timeline_ts)).to_numpy(), index=timeline_ts.index)


class MissingInput(ValueError):
    """A required input file, column or overlapping time range is missing (defect #6)."""


# Standard column names per source. Aliases map legacy fetcher output to the standard names.
SCHEMAS = {
    "demand":       {"required": ["timestamp", "demand_mw"], "aliases": {"value": "demand_mw"}},
    "weather":      {"required": ["timestamp", "temp_f"], "aliases": {}},
    "prices":       {"required": ["timestamp", "price_mwh"], "aliases": {"value": "price_mwh", "price": "price_mwh"}},
    "gas":          {"required": ["date", "gas_price"], "aliases": {"price": "gas_price"}},
    "site_load":    {"required": ["timestamp", "site_load_mw"], "aliases": {"load_mw": "site_load_mw"}},
    "avoided_cost": {"required": ["timestamp", "avoided_cost_mwh"], "aliases": {"price_mwh": "avoided_cost_mwh"}},
}


def _load_source(name, path, *, required, assume_tz=None, as_day_start_tz=None, announce_missing=True):
    """Read one input CSV, standardize column names, convert time to tz-aware UTC.

    Missing file: None (or MissingInput if required). Unreadable file, missing required columns,
    or no usable rows when required: MissingInput. Only rows missing a *required* value are dropped.
    """
    if not os.path.exists(path):
        if required:
            raise MissingInput(f"{name}: required input {path} not found.")
        if announce_missing:
            print(f"ℹ️ {name}: {path.name} not found; its columns will be empty.")
        return None
    schema = SCHEMAS[name]
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise MissingInput(f"{name}: cannot read {path}: {e}") from e
    df = df.rename(columns={a: s for a, s in schema["aliases"].items() if a in df.columns and s not in df.columns})
    missing = [c for c in schema["required"] if c not in df.columns]
    if missing:
        raise MissingInput(f"{name}: {path.name} lacks required column(s) {missing}; found {list(df.columns)}.")
    df = df.dropna(subset=schema["required"]).reset_index(drop=True)
    ts_col = schema["required"][0]
    if as_day_start_tz:
        df[ts_col] = dates_to_utc_day_start(df[ts_col], as_day_start_tz)
    else:
        df[ts_col] = series_to_utc(df[ts_col], assume_tz)
    if df.empty and required:
        raise MissingInput(f"{name}: {path.name} has no usable rows.")
    return df


def merge_inputs(cfg: dict, paths: Paths, now: datetime | None = None) -> pd.DataFrame:
    """Merge demand, gas, weather and prices into paths.merged_inputs. `now` is injectable for tests."""
    ops = cfg.get("operations", {})
    gas_basis = float(cfg.get("gas", {}).get("basis_adder_per_mmbtu", 0.0))

    tz = market_tz(cfg)
    now = now_utc(now, tz)
    window_start = now - timedelta(days=LOOKBACK_DAYS)
    window_end = now + timedelta(days=LOOKAHEAD_DAYS)

    program_mode = ops.get("program_mode", "WHOLESALE")
    need_prices = program_mode == "WHOLESALE" or (program_mode == "DR" and ops.get("dr_event_revenue_per_mwh") is None)
    need_gas = bool(cfg.get("generators"))

    demand = _load_source("demand", paths.demand, required=False, assume_tz="UTC")
    weather = _load_source("weather", paths.merged_weather, required=False)
    prices = _load_source("prices", paths.market_price, required=need_prices)
    gas = _load_source("gas", paths.gas, required=need_gas, as_day_start_tz=tz)
    if gas is not None:
        gas = gas.rename(columns={"date": "timestamp"})

    # Decide frequency
    steps = []
    for df in (demand, weather, prices):
        if df is not None and not df.empty:
            steps.append(_min_step_seconds(df["timestamp"]))
    freq = _target_freq(steps) if steps else "h"

    # Window
    ts_min, ts_max = window_start, window_end
    for df in (demand, weather, prices):
        if df is not None and not df.empty:
            ts_min = max(ts_min, df["timestamp"].min())
            ts_max = min(ts_max, df["timestamp"].max())
    if freq == "15min":
        ts_min = pd.to_datetime(ts_min).ceil("15min")
        ts_max = pd.to_datetime(ts_max).floor("15min")

    if ts_min > ts_max:
        raise MissingInput(
            f"No data overlaps the merge window {window_start} .. {window_end} (UTC) after intersecting "
            "demand/weather/price coverage. Refresh the data or pass --as-of for a historical window."
        )
    timeline = pd.DataFrame({"timestamp": pd.date_range(ts_min, ts_max, freq=freq)})

    # Gas -> every step of its local day (+ carry over non-trading days)
    merged = timeline.copy()
    if gas is not None and not gas.empty:
        merged["gas_price"] = _gas_on_timeline(gas, merged["timestamp"])
    else:
        merged["gas_price"] = np.nan
    merged["gas_price_effective"] = pd.to_numeric(merged["gas_price"], errors="coerce") + gas_basis

    # Demand, Price, Weather
    if demand is not None and not demand.empty:
        d = _resample_ffill(demand, freq)
        merged = merged.merge(d[["timestamp", "demand_mw"]], on="timestamp", how="left")
    else:
        merged["demand_mw"] = merged.get("demand_mw", np.nan)

    if prices is not None and not prices.empty:
        p = _resample_ffill(prices, freq)
        merged = merged.merge(p[["timestamp", "price_mwh"]], on="timestamp", how="left")
    else:
        merged["price_mwh"] = merged.get("price_mwh", np.nan)

    if weather is not None and not weather.empty:
        w = _resample_ffill(weather, freq)
        cols = [c for c in ["temp_f", "condition", "windSpeed", "temperatureUnit"] if c in w.columns]
        if cols:
            merged = merged.merge(w[["timestamp"] + cols], on="timestamp", how="left")

    # Optional series
    site_load = _load_source("site_load", paths.site_load, required=False, assume_tz=tz, announce_missing=False)
    if site_load is not None and not site_load.empty:
        sl = _resample_ffill(site_load, freq)
        merged = merged.merge(sl[["timestamp", "site_load_mw"]], on="timestamp", how="left")
    else:
        merged["site_load_mw"] = merged.get("site_load_mw", np.nan)

    avoided = _load_source("avoided_cost", paths.avoided_cost, required=False, assume_tz=tz, announce_missing=False)
    if avoided is not None and not avoided.empty:
        ac = _resample_ffill(avoided, freq)
        merged = merged.merge(ac[["timestamp", "avoided_cost_mwh"]], on="timestamp", how="left")

    # Robust fill for avoided_cost_mwh — always operate on a Series
    fixed_ac = float(ops.get("avoided_cost_fixed_per_mwh", 65.0))
    if "avoided_cost_mwh" in merged.columns:
        ac_series = pd.to_numeric(merged["avoided_cost_mwh"], errors="coerce")
        merged["avoided_cost_mwh"] = ac_series.fillna(fixed_ac)
    else:
        merged["avoided_cost_mwh"] = fixed_ac

    # Constraint windows from config + CSVs
    fuel_windows = ops.get("fuel_curtailment_windows", []) + _load_windows_csv(paths.fuel_curtailments)
    dr_windows = ops.get("dr_event_windows", []) + _load_windows_csv(paths.dr_events)
    ppa_windows = ops.get("ppa_windows", [])

    idx = merged["timestamp"]

    # Export cap
    export_mode = ops.get("export_mode", "full_export")
    export_cap = float(ops.get("export_cap_mw", 9999))
    if export_mode == "non_export":
        merged["export_cap_mw"] = 0.0
    elif export_mode == "limited_export":
        merged["export_cap_mw"] = export_cap
    else:
        merged["export_cap_mw"] = 9999.0 if export_cap >= 9999 else export_cap

    # Permit, Fuel, Events, PPA
    permit_class = ops.get("permit_class", "non_emergency")
    merged["permit_allowed"] = 0 if permit_class == "emergency" else 1

    fuel_contract = ops.get("fuel_contract", "firm")
    fuel_mask = _flag_windows(idx, fuel_windows, tz)
    merged["fuel_available"] = (1 - fuel_mask).astype(int) if fuel_contract == "interruptible" else 1

    merged["event_active"] = _flag_windows(idx, dr_windows, tz)
    if ppa_windows:
        merged["ppa_active"] = _flag_windows(idx, ppa_windows, tz)
    else:
        merged["ppa_active"] = 1 if ops.get("program_mode", "WHOLESALE") in ("PURPA", "NET_METERING") else 0

    merged = merged.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    merged.to_csv(paths.merged_inputs, index=False)
    print(f"✅ Saved {paths.merged_inputs.name} with {len(merged)} rows • freq={freq}")
    return merged
