"""Gas genset dispatch simulation. Ported from legacy simulate_generator.py; behavior unchanged.

Heat rate is config Btu/kWh; converted once via gensim.units (defect #7).

Dispatch rules (defect #8):
  * runs only when margin > min_margin_threshold (strict) and all hard gates allow it;
  * hard gates (permit, fuel availability, program/PPA window, generator maintenance windows)
    force the unit off immediately, overriding min-up; min up/down apply to economic decisions;
  * output is capped at capacity x availability_cap and by export/site limits.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from gensim.config import Paths
from gensim.units import fuel_cost_per_mwh
from gensim.windows import flag_windows


def _safe_gate(df, col, default=0):
    if col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce").fillna(default)
    else:
        s = pd.Series(default, index=df.index)
    return s.astype(int)


def simulate(cfg: dict, paths: Paths, now: datetime | None = None) -> pd.DataFrame:
    """Dispatch each configured generator over paths.merged_inputs -> paths.simulation_results."""
    CONFIG = cfg
    generators = CONFIG.get("generators", [])
    ops = CONFIG.get("operations", {})

    df = pd.read_csv(paths.merged_inputs, parse_dates=["timestamp"]).sort_values("timestamp")

    # dt_hours
    dt = df["timestamp"].diff().dt.total_seconds().bfill().fillna(3600)/3600.0
    df["dt_hours"] = dt.clip(lower=1e-6)

    # Program mode → select revenue series + program gate
    program_mode = ops.get("program_mode", "WHOLESALE")
    price_market = pd.to_numeric(df.get("price_mwh", pd.Series(np.nan, index=df.index)), errors="coerce")
    avoided_cost = pd.to_numeric(df.get("avoided_cost_mwh", pd.Series(np.nan, index=df.index)), errors="coerce")
    event_active = _safe_gate(df, "event_active", 0)
    ppa_active   = _safe_gate(df, "ppa_active", 0)

    if program_mode == "WHOLESALE":
        revenue_series = price_market
        program_gate = pd.Series(1, index=df.index, dtype=int)
    elif program_mode in ("PURPA","NET_METERING"):
        revenue_series = avoided_cost.ffill()
        program_gate = ppa_active
    elif program_mode == "DR":
        dr_rev = ops.get("dr_event_revenue_per_mwh", None)
        revenue_series = pd.Series(float(dr_rev), index=df.index) if dr_rev is not None else price_market
        program_gate = event_active
    else:
        revenue_series = price_market
        program_gate = pd.Series(1, index=df.index, dtype=int)

    permit_allowed = _safe_gate(df, "permit_allowed", 1)
    fuel_available = _safe_gate(df, "fuel_available", 1)
    allowed = (permit_allowed.astype(bool) & fuel_available.astype(bool) & program_gate.astype(bool)).astype(int)

    export_mode = ops.get("export_mode","full_export")
    export_cap = pd.to_numeric(df.get("export_cap_mw", pd.Series(9999.0, index=df.index)), errors="coerce").fillna(9999.0)
    site_load  = pd.to_numeric(df.get("site_load_mw", pd.Series(np.nan, index=df.index)), errors="coerce")

    for gen in generators:
        name = gen["name"]
        heat_rate = float(gen["heat_rate_btu_per_kwh"])
        capacity = float(gen["capacity_mw"])
        threshold = float(gen["min_margin_threshold"])
        vom = float(gen.get("vom_per_mwh", 0.0))
        start_cost = float(gen.get("start_cost", 0.0))
        avail = float(gen.get("availability_cap", 1.0))

        eff_cap = max(0.0, min(capacity*avail, capacity))

        gas_col = "gas_price_effective" if "gas_price_effective" in df.columns else "gas_price"
        fuel_cost = fuel_cost_per_mwh(heat_rate, pd.to_numeric(df[gas_col], errors="coerce").ffill().bfill().fillna(0.0))
        margin = (revenue_series.ffill().bfill() - fuel_cost - vom).fillna(-1e9)

        # Max dispatch based on export/site limits
        if export_mode == "non_export":
            max_cap = site_load.fillna(0.0)
        elif export_mode == "limited_export":
            max_cap = site_load.fillna(0.0) + export_cap
        else:
            max_cap = export_cap
        max_cap = max_cap.clip(lower=0.0, upper=eff_cap)

        out_col, prof_col, run_col, mar_col = f"{name}_output_mw", f"{name}_profit", f"{name}_run", f"{name}_margin_per_mwh"
        df[out_col] = 0.0; df[prof_col] = 0.0; df[run_col] = False; df[mar_col] = margin

        # Ramp settings
        ramp_minutes = gen.get("ramp_to_full_minutes")
        ramp_rate_mw_per_hr = float(gen.get("ramp_rate_mw_per_hr", 0.0))
        if ramp_minutes is not None and float(ramp_minutes) > 0:
            ramp_rate_mw_per_hr = eff_cap / (float(ramp_minutes) / 60.0)
        if ramp_rate_mw_per_hr <= 0: ramp_rate_mw_per_hr = eff_cap * 1e6

        current_output = 0.0
        on_state = False
        hours_since_change = 1e9
        min_up = int(gen.get("min_up_hours", 0))
        min_down = int(gen.get("min_down_hours", 0))
        in_maintenance = flag_windows(df["timestamp"], gen.get("maintenance_windows", [])).astype(bool)

        for i in range(len(df)):
            econ = float(margin.iloc[i]) > threshold
            hard_ok = bool(allowed.iloc[i]) and not bool(in_maintenance.iloc[i])

            dt_h = float(df.at[i,"dt_hours"])

            decision_on = on_state
            if not hard_ok:
                decision_on = False                      # forced off; overrides min-up
            elif on_state:
                if not econ and hours_since_change >= max(min_up,0):
                    decision_on = False
            else:
                if econ and hours_since_change >= max(min_down,0):
                    decision_on = True

            target_cap = float(max_cap.iloc[i]) if decision_on else 0.0
            if not hard_ok:
                output = 0.0                             # outage/curtailment: no ramp-down tail
            else:
                delta = target_cap - current_output
                max_step = ramp_rate_mw_per_hr * dt_h
                change = max(-max_step, min(max_step, delta))
                output = max(0.0, min(target_cap, current_output + change))

            started = (not on_state) and decision_on
            df.at[i, out_col] = output
            df.at[i, run_col] = output > 0.0
            interval_profit = output * float(margin.iloc[i]) * dt_h
            if started and start_cost > 0.0: interval_profit -= start_cost
            df.at[i, prof_col] = interval_profit

            if decision_on == on_state: 
                hours_since_change += dt_h
            else:
                on_state = decision_on
                hours_since_change = 0.0
            current_output = output

    df.to_csv(paths.simulation_results, index=False)
    print(f"✅ Saved {paths.simulation_results.name} with {len(df)} rows and {len(generators)} generators simulated")

    stamp = now if now is not None else datetime.now()
    with open(paths.last_updated, "w") as f:
        f.write(stamp.strftime("%Y-%m-%d %H:%M:%S"))
    return df
