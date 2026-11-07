"""Run-of-river hydro: daily flow -> daily energy. See docs/calibration_protocol.md.

    Q_usable = clamp(Q_gauge - Q_minflow, 0, Q_max)            [cfs]
    P_MW     = min(rho*g * Q_usable[m3/s] * (H*eta)[m] / 1e6, P_cap)
    MWh_day  = P_MW * 24 * availability
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

CFS_TO_M3S = 0.0283168
FT_TO_M = 0.3048
G = 9.81            # rho*g/1000 with rho = 1000 kg/m3 -> kW per (m3/s * m)


@dataclass(frozen=True)
class HydroParams:
    head_eff_ft: float          # net head x efficiency, ft (combined; H*eta)
    q_max_cfs: float            # total turbine hydraulic capacity
    q_minflow_cfs: float        # flow not available to the units (leakage, required releases)
    availability: float         # fraction of potential energy actually produced
    p_cap_mw: float             # plant output cap

    def as_dict(self) -> dict:
        return asdict(self)


def power_mw(q_cfs, p: HydroParams):
    q = np.asarray(q_cfs, dtype=float)
    usable = np.clip(q - p.q_minflow_cfs, 0.0, p.q_max_cfs)
    mw = G * usable * CFS_TO_M3S * p.head_eff_ft * FT_TO_M / 1000.0
    return np.minimum(mw, p.p_cap_mw)


def daily_energy(flow: pd.DataFrame, p: HydroParams) -> pd.DataFrame:
    """flow: columns date (YYYY-MM-DD), q_cfs -> adds p_mw, mwh (NaN where flow is missing)."""
    out = flow[["date", "q_cfs"]].copy()
    out["p_mw"] = power_mw(out["q_cfs"], p)
    out.loc[out["q_cfs"].isna(), "p_mw"] = np.nan
    out["mwh"] = out["p_mw"] * 24.0 * p.availability
    return out


def monthly_energy(flow: pd.DataFrame, p: HydroParams) -> pd.DataFrame:
    """-> month (YYYY-MM), model_mwh (sum of daily), q_mean_cfs, days, missing_days."""
    d = daily_energy(flow, p)
    d["month"] = d["date"].str[:7]
    g = d.groupby("month")
    out = pd.DataFrame({
        "model_mwh": g["mwh"].sum(min_count=1),
        "q_mean_cfs": g["q_cfs"].mean(),
        "days": g["date"].count(),
        "missing_days": g["q_cfs"].apply(lambda s: int(s.isna().sum())),
    }).reset_index()
    # days absent from the record entirely also count as missing
    n_in_month = pd.to_datetime(out["month"] + "-01").dt.days_in_month
    out["missing_days"] = out["missing_days"] + (n_in_month - out["days"]).clip(lower=0)
    return out
