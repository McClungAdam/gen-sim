import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

CONFIG_PATH = "config.json"
LOOKBACK_DAYS = 45
LOOKAHEAD_DAYS = 14

SITE_LOAD_FILE     = "site_load.csv"        # optional: timestamp,load_mw
AVOIDED_COST_FILE  = "avoided_cost.csv"     # optional: timestamp,price_mwh
CURTAILMENTS_FILE  = "fuel_curtailments.csv"# optional: start,end,note
EVENTS_FILE        = "dr_events.csv"        # optional: start,end,note

def load_config(path=CONFIG_PATH):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def _min_step_seconds(ts):
    ser = pd.to_datetime(ts).sort_values().dropna()
    diffs = ser.diff().dt.total_seconds()
    diffs = diffs[diffs > 0]
    return float(diffs.min()) if not diffs.empty else float("inf")

def _target_freq(steps):
    return "15min" if any(s < 3600 for s in steps if s != float("inf")) else "H"

def _flag_windows(index_ts, windows):
    if not windows:
        return pd.Series(0, index=index_ts, dtype=int)
    mask = pd.Series(0, index=index_ts, dtype=int)
    for w in windows:
        try:
            s = pd.to_datetime(w.get("start")); e = pd.to_datetime(w.get("end"))
            if pd.isna(s) or pd.isna(e): 
                continue
            mask |= ((index_ts >= s) & (index_ts < e)).astype(int)
        except Exception:
            continue
    return mask

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

def merge_inputs(
    demand_file="duke_demand.csv",
    gas_file="henry_hub_daily.csv",
    weather_file="merged_weather.csv",
    price_file="market_price.csv",
    output_file="merged_inputs.csv"
):
    cfg = load_config()
    ops = cfg.get("operations", {})
    gas_basis = float(cfg.get("gas", {}).get("basis_adder_per_mmbtu", 0.0))

    now = datetime.now()
    window_start = now - timedelta(days=LOOKBACK_DAYS)
    window_end   = now + timedelta(days=LOOKAHEAD_DAYS)

    # Load core inputs
    def load_csv(fname, parse_dates):
        if not os.path.exists(fname): 
            return None
        try:
            return pd.read_csv(fname, parse_dates=parse_dates).dropna()
        except Exception:
            return None

    demand  = load_csv(demand_file, ["timestamp"])
    weather = load_csv(weather_file, ["timestamp"])
    prices  = load_csv(price_file, ["timestamp"])
    gas     = load_csv(gas_file, ["date"])

    if demand is not None and "value" in demand.columns:
        demand = demand.rename(columns={"value": "demand_mw"})
    if prices is not None:
        if "value" in prices.columns: prices = prices.rename(columns={"value": "price_mwh"})
        if "price" in prices.columns: prices = prices.rename(columns={"price": "price_mwh"})
    if gas is not None:
        gas = gas.rename(columns={"date": "timestamp", "price": "gas_price"})

    # Decide frequency
    steps = []
    for df in (demand, weather, prices):
        if df is not None and not df.empty:
            steps.append(_min_step_seconds(df["timestamp"]))
    freq = _target_freq(steps) if steps else "H"

    # Window
    ts_min, ts_max = window_start, window_end
    for df in (demand, weather, prices):
        if df is not None and not df.empty:
            ts_min = max(ts_min, df["timestamp"].min())
            ts_max = min(ts_max, df["timestamp"].max())
    if freq == "15min":
        ts_min = pd.to_datetime(ts_min).ceil("15min")
        ts_max = pd.to_datetime(ts_max).floor("15min")

    timeline = pd.DataFrame({"timestamp": pd.date_range(ts_min, ts_max, freq=freq)})

    # Gas -> resample
    if gas is not None:
        gas = _resample_ffill(gas, freq)
        merged = timeline.merge(gas, on="timestamp", how="left")
    else:
        merged = timeline.copy()
        merged["gas_price"] = np.nan
    merged["gas_price_effective"] = pd.to_numeric(merged["gas_price"], errors="coerce") + gas_basis

    # Demand, Price, Weather
    if demand is not None and not demand.empty:
        d = _resample_ffill(demand, freq)
        merged = merged.merge(d[["timestamp","demand_mw"]], on="timestamp", how="left")
    else:
        merged["demand_mw"] = merged.get("demand_mw", np.nan)

    if prices is not None and not prices.empty:
        p = _resample_ffill(prices, freq)
        merged = merged.merge(p[["timestamp","price_mwh"]], on="timestamp", how="left")
    else:
        merged["price_mwh"] = merged.get("price_mwh", np.nan)

    if weather is not None and not weather.empty:
        w = _resample_ffill(weather, freq)
        cols = [c for c in ["temp_f","condition","windSpeed","temperatureUnit"] if c in w.columns]
        if cols:
            merged = merged.merge(w[["timestamp"]+cols], on="timestamp", how="left")

    # Optional series
    site_load = load_csv(SITE_LOAD_FILE, ["timestamp"])
    if site_load is not None and not site_load.empty:
        if "load_mw" in site_load.columns:
            site_load = site_load.rename(columns={"load_mw":"site_load_mw"})
        sl = _resample_ffill(site_load, freq)
        merged = merged.merge(sl[["timestamp","site_load_mw"]], on="timestamp", how="left")
    else:
        merged["site_load_mw"] = merged.get("site_load_mw", np.nan)

    avoided = load_csv(AVOIDED_COST_FILE, ["timestamp"])
    if avoided is not None and not avoided.empty:
        if "price_mwh" in avoided.columns:
            avoided = avoided.rename(columns={"price_mwh":"avoided_cost_mwh"})
        ac = _resample_ffill(avoided, freq)
        merged = merged.merge(ac[["timestamp","avoided_cost_mwh"]], on="timestamp", how="left")

    # Robust fill for avoided_cost_mwh — always operate on a Series
    fixed_ac = float(ops.get("avoided_cost_fixed_per_mwh", 65.0))
    if "avoided_cost_mwh" in merged.columns:
        ac_series = pd.to_numeric(merged["avoided_cost_mwh"], errors="coerce")
        merged["avoided_cost_mwh"] = ac_series.fillna(fixed_ac)
    else:
        merged["avoided_cost_mwh"] = fixed_ac

    # Constraint windows from config + CSVs
    fuel_windows = ops.get("fuel_curtailment_windows", []) + _load_windows_csv(CURTAILMENTS_FILE)
    dr_windows   = ops.get("dr_event_windows", []) + _load_windows_csv(EVENTS_FILE)
    ppa_windows  = ops.get("ppa_windows", [])

    idx = pd.to_datetime(merged["timestamp"])

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
    fuel_mask = _flag_windows(idx, fuel_windows)
    merged["fuel_available"] = (1 - fuel_mask).astype(int) if fuel_contract == "interruptible" else 1

    merged["event_active"] = _flag_windows(idx, dr_windows)
    if ppa_windows:
        merged["ppa_active"] = _flag_windows(idx, ppa_windows)
    else:
        merged["ppa_active"] = 1 if ops.get("program_mode","WHOLESALE") in ("PURPA","NET_METERING") else 0

    merged = merged.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    merged.to_csv(output_file, index=False)
    print(f"✅ Saved {output_file} with {len(merged)} rows • freq={freq}")

if __name__ == "__main__":
    merge_inputs()
