"""Calibration machinery: recovers known parameters from synthetic data; scenario percentiles."""
import numpy as np
import pandas as pd
import pytest

from gensim.assets.hydro_ror import HydroParams, monthly_energy
from gensim.calibration import hydro_calibrate as hc
from gensim.calibration import rules


def _synthetic_flow():
    days = pd.date_range("1930-01-01", "2024-08-31", freq="D")
    rng = np.random.default_rng(7)
    seasonal = 1900 + 900 * np.cos(2 * np.pi * (days.day_of_year - 60) / 365.25)
    q = seasonal * np.exp(rng.normal(0, 0.45, len(days)))
    return pd.DataFrame({"date": days.strftime("%Y-%m-%d"), "q_cfs": q})


def test_fit_recovers_scale_and_qmax():
    flow = _synthetic_flow()
    truth = HydroParams(head_eff_ft=30.0, q_max_cfs=1800.0, q_minflow_cfs=10.0, availability=0.95, p_cap_mw=5.0)
    actual = monthly_energy(flow, truth)[["month", "model_mwh"]].rename(columns={"model_mwh": "net_generation_mwh"})
    actual = actual[actual["month"].between("2001-01", "2024-08")]
    r = hc.run(flow, actual)
    eff_true = truth.head_eff_ft * truth.availability
    assert r.params.head_eff_ft * r.params.availability == pytest.approx(eff_true, rel=0.02)
    assert r.params.q_max_cfs == pytest.approx(1800.0, rel=0.03)
    assert r.metrics["calibrate"]["monthly_r"] > 0.999
    assert r.exceedance["P90_mwh"] < r.exceedance["P50_mwh"] < r.exceedance["P10_mwh"]


def test_water_years_complete_only():
    flow = _synthetic_flow()
    wy, exc = hc.water_year_scenarios(flow, rules.PRIOR)
    assert wy["days"].min() >= 365 and exc["n"] == len(wy)
    assert wy["wy"].max() == 2023   # WY2024 (Oct 2023-Sep 2024) is incomplete: data end 2024-08-31
