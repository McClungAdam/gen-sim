"""Mechanical exclusion rules from docs/calibration_protocol.md (written before any fit).

Do not tune these to the fit result. Any change needs its own commit explaining why.
"""
from __future__ import annotations

import pandas as pd

from gensim.assets.hydro_ror import HydroParams, monthly_energy

GROSS_HEAD_FT = 2188.27 - 2148.50                       # FERC EA: pool crest - normal tailrace
PRIOR = HydroParams(head_eff_ft=0.80 * GROSS_HEAD_FT, q_max_cfs=2050.0, q_minflow_cfs=10.0,
                    availability=1.0, p_cap_mw=5.0)
NAMEPLATE_MW = 5.4
KNOWN_OUTAGE_FROM = "2024-09"                           # R1: Hurricane Helene
MAX_MISSING_FLOW_DAYS = 3                               # R2
DERATE_RATIO = 0.50                                     # R4
FLOW_BAND = (0.05, 0.95)                                # R4: same-calendar-month mean-flow percentiles
FLOW_BAND_YEARS = (1930, 2023)

CALIBRATE = ("2003-01", "2012-12")
VALIDATE = ("2013-01", "2023-12")


def monthly_table(flow: pd.DataFrame, actual: pd.DataFrame, prior: HydroParams = PRIOR) -> pd.DataFrame:
    """Join flow-derived prior model with EIA actuals and apply R1-R4. One row per month with actuals."""
    m = monthly_energy(flow, prior).rename(columns={"model_mwh": "prior_model_mwh"})
    t = actual.merge(m, on="month", how="left")
    t["hours"] = pd.to_datetime(t["month"] + "-01").dt.days_in_month * 24

    # flow band per calendar month from the whole-record monthly means
    ref = m[(m["month"].str[:4].astype(int) >= FLOW_BAND_YEARS[0]) & (m["month"].str[:4].astype(int) <= FLOW_BAND_YEARS[1])]
    ref = ref.assign(cal=ref["month"].str[5:7])
    band = ref.groupby("cal")["q_mean_cfs"].quantile(list(FLOW_BAND)).unstack()
    band.columns = ["q_lo", "q_hi"]
    t = t.assign(cal=t["month"].str[5:7]).merge(band, left_on="cal", right_index=True, how="left")

    reasons = []
    for r in t.itertuples():
        if r.month >= KNOWN_OUTAGE_FROM:
            reasons.append("R1 known outage (Helene)")
        elif pd.isna(r.net_generation_mwh) or pd.isna(r.missing_days) or r.missing_days > MAX_MISSING_FLOW_DAYS:
            reasons.append("R2 missing data")
        elif r.net_generation_mwh > NAMEPLATE_MW * r.hours:
            reasons.append("R3 above nameplate")
        elif (r.net_generation_mwh < DERATE_RATIO * r.prior_model_mwh) and (r.q_lo <= r.q_mean_cfs <= r.q_hi):
            reasons.append(f"R4 actual < {DERATE_RATIO:.0%} of prior model at normal flow")
        else:
            reasons.append("")
    t["exclude_reason"] = reasons
    t["excluded"] = t["exclude_reason"] != ""
    t["period"] = "other"
    t.loc[t["month"].between(*CALIBRATE), "period"] = "calibrate"
    t.loc[t["month"].between(*VALIDATE), "period"] = "validate"
    return t.drop(columns=["cal"])


def flagged_years(table: pd.DataFrame) -> pd.Series:
    """year -> '; '.join(distinct reasons) for years with any excluded month."""
    ex = table[table["excluded"]].assign(year=lambda d: d["month"].str[:4])
    return ex.groupby("year")["exclude_reason"].apply(lambda s: "; ".join(sorted({x.split(' ')[0] for x in s})))


# ---------------------------------------------------------------- protocol v2 (annual)
# docs/calibration_protocol_v2.md. Written before the v2 refit; thresholds carried over from v1.
from dataclasses import replace as _replace  # noqa: E402

PRIOR_V2 = _replace(PRIOR, availability=1.0)
V2_KNOWN_OUTAGE_FROM_YEAR = 2024                 # A1
V2_MAX_MISSING_FLOW_DAYS = 10                    # A2
V2_CALIBRATE = (2003, 2012)
V2_VALIDATE = (2013, 2018)
V2_MONTHLY_CHECK = ("2017-01", "2018-12")
V2_AS_OPERATED = (2019, 2023)


def annual_table(flow: pd.DataFrame, actual: pd.DataFrame, prior: HydroParams = PRIOR_V2) -> pd.DataFrame:
    """One row per calendar year with EIA data: actual, prior model, mean flow, A1-A4 reason, period."""
    m = monthly_energy(flow, prior)
    m["year"] = m["month"].str[:4].astype(int)
    fy = m.groupby("year").agg(prior_model_mwh=("model_mwh", "sum"), missing_flow_days=("missing_days", "sum"))
    d = flow.assign(year=flow["date"].str[:4].astype(int)).groupby("year")["q_cfs"].mean().rename("q_mean_cfs")
    fy = fy.join(d)
    ref = fy.loc[FLOW_BAND_YEARS[0]:FLOW_BAND_YEARS[1], "q_mean_cfs"]
    q_lo, q_hi = ref.quantile(FLOW_BAND[0]), ref.quantile(FLOW_BAND[1])

    a = actual.assign(year=actual["month"].str[:4].astype(int))
    ay = a.groupby("year").agg(actual_mwh=("net_generation_mwh", lambda s: s.sum(min_count=1)),
                               eia_months=("net_generation_mwh", "count")).join(fy, how="left").reset_index()
    ay["hours"] = [8784 if pd.Timestamp(year=y, month=1, day=1).is_leap_year else 8760 for y in ay["year"]]

    reasons = []
    for r in ay.itertuples():
        if r.year >= V2_KNOWN_OUTAGE_FROM_YEAR:
            reasons.append("A1 known outage (Helene)")
        elif r.eia_months < 12 or pd.isna(r.missing_flow_days) or r.missing_flow_days > V2_MAX_MISSING_FLOW_DAYS:
            reasons.append("A2 incomplete data")
        elif r.actual_mwh > NAMEPLATE_MW * r.hours:
            reasons.append("A3 above nameplate")
        elif r.actual_mwh < DERATE_RATIO * r.prior_model_mwh and q_lo <= r.q_mean_cfs <= q_hi:
            reasons.append(f"A4 actual < {DERATE_RATIO:.0%} of prior model at normal flow")
        else:
            reasons.append("")
    ay["exclude_reason"] = reasons
    ay["excluded"] = ay["exclude_reason"] != ""
    ay["period"] = "other"
    for lo, hi, name in ((*V2_CALIBRATE, "calibrate"), (*V2_VALIDATE, "validate"), (*V2_AS_OPERATED, "as_operated")):
        ay.loc[ay["year"].between(lo, hi), "period"] = name
    ay["q_band_lo"], ay["q_band_hi"] = q_lo, q_hi
    return ay
