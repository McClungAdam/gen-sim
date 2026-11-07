"""Run-of-river model physics and the pre-registered exclusion rules."""
import numpy as np
import pandas as pd
import pytest

from gensim.assets.hydro_ror import HydroParams, daily_energy, monthly_energy, power_mw
from gensim.calibration import rules

P = HydroParams(head_eff_ft=32.0, q_max_cfs=2000.0, q_minflow_cfs=10.0, availability=0.9, p_cap_mw=5.0)


def test_power_formula_hand_check():
    # 1,000 cfs usable * 0.0283168 = 28.3168 m3/s; 32 ft = 9.7536 m; 9.81*28.3168*9.7536/1000 = 2.7094 MW
    assert power_mw([1010.0], P)[0] == pytest.approx(2.70947, rel=1e-4)


def test_minflow_qmax_and_cap():
    assert power_mw([5.0], P)[0] == 0.0                          # below minflow
    big = HydroParams(64.0, 3000.0, 0.0, 1.0, 5.0)
    assert power_mw([2500.0], big)[0] == 5.0                     # capped at P_cap
    assert power_mw([5000.0], P)[0] == pytest.approx(power_mw([2010.0], P)[0])   # Q_max clamp


def test_daily_and_monthly_energy():
    flow = pd.DataFrame({"date": ["2003-01-01", "2003-01-02", "2003-02-01"], "q_cfs": [1010.0, np.nan, 1010.0]})
    d = daily_energy(flow, P)
    assert d["mwh"].iloc[0] == pytest.approx(2.70947 * 24 * 0.9, rel=1e-4) and np.isnan(d["mwh"].iloc[1])
    m = monthly_energy(flow, P).set_index("month")
    assert m.loc["2003-01", "missing_days"] == 30       # 1 NaN + 29 absent days
    assert m.loc["2003-02", "missing_days"] == 27


def _flow(months, q):
    days = pd.concat([pd.Series(pd.date_range(f"{m}-01", periods=pd.Period(m).days_in_month, freq="D")) for m in months])
    return pd.DataFrame({"date": days.dt.strftime("%Y-%m-%d"), "q_cfs": q})


def test_rules_r1_to_r4():
    months = [f"{y}-06" for y in range(1930, 2025)]            # many Junes -> a real flow band
    flow = _flow(months, 1000.0)
    prior_june = monthly_energy(_flow(["2003-06"], 1000.0), rules.PRIOR)["model_mwh"].iloc[0]
    actual = pd.DataFrame({"month": ["2003-06", "2004-06", "2005-06", "2006-06", "2024-06", "2024-09"],
                           "net_generation_mwh": [0.9 * prior_june, 0.3 * prior_june, 9999.0, np.nan, 0.9 * prior_june, 0.0]})
    flow = flow[~flow["date"].str.startswith("2024-09")]
    t = rules.monthly_table(flow, actual).set_index("month")
    assert t.loc["2003-06", "exclude_reason"] == ""
    assert t.loc["2004-06", "exclude_reason"].startswith("R4")
    assert t.loc["2005-06", "exclude_reason"].startswith("R3")
    assert t.loc["2006-06", "exclude_reason"].startswith("R2")
    assert t.loc["2024-06", "exclude_reason"] == ""             # before Helene
    assert t.loc["2024-09", "exclude_reason"].startswith("R1")
    assert t.loc["2003-06", "period"] == "calibrate" and t.loc["2024-06", "period"] == "other"


def test_r4_not_applied_outside_flow_band():
    # a drought month far below the band is not an outage even if actual << prior model
    months = [f"{y}-08" for y in range(1930, 2024)]
    q = np.concatenate([np.full(31, 1000.0 + 10 * i) for i in range(len(months))])
    flow = _flow(months, q)
    flow.loc[flow["date"].str.startswith("2007-08"), "q_cfs"] = 100.0
    actual = pd.DataFrame({"month": ["2007-08"], "net_generation_mwh": [1.0]})
    t = rules.monthly_table(flow, actual)
    assert t["exclude_reason"].iloc[0] == ""


def test_prior_constants_match_protocol():
    assert rules.GROSS_HEAD_FT == pytest.approx(39.77)
    assert rules.PRIOR.q_max_cfs == 2050 and rules.PRIOR.p_cap_mw == 5.0 and rules.DERATE_RATIO == 0.5


def test_v2_annual_rules():
    years = range(1930, 2025)
    days = pd.date_range("1930-01-01", "2024-12-31", freq="D")
    flow = pd.DataFrame({"date": days.strftime("%Y-%m-%d"), "q_cfs": 1500.0 + (days.year - 1930) * 2.0})
    prior_2005 = rules.annual_table(flow, pd.DataFrame({"month": [f"2005-{m:02d}" for m in range(1, 13)], "net_generation_mwh": 1.0}))
    pm = prior_2005["prior_model_mwh"].iloc[0]
    rows = []
    for y, val in [(2005, 0.9 * pm), (2006, 0.3 * pm), (2007, 99999.0), (2024, 0.9 * pm)]:
        rows += [{"month": f"{y}-{m:02d}", "net_generation_mwh": val / 12} for m in range(1, 13)]
    rows += [{"month": f"2008-{m:02d}", "net_generation_mwh": 1000.0} for m in range(1, 12)]   # 11 months only
    t = rules.annual_table(flow, pd.DataFrame(rows)).set_index("year")
    assert t.loc[2005, "exclude_reason"] == "" and t.loc[2005, "period"] == "calibrate"
    assert t.loc[2006, "exclude_reason"].startswith("A4")
    assert t.loc[2007, "exclude_reason"].startswith("A3")
    assert t.loc[2008, "exclude_reason"].startswith("A2")
    assert t.loc[2024, "exclude_reason"].startswith("A1")
    assert rules.PRIOR_V2.availability == 1.0
