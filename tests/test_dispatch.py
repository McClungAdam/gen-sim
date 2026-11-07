"""Defect #8: dispatch honors threshold, maintenance, availability and hard gates."""
import pandas as pd
import pytest

from gensim.assets.gas_genset import simulate
from gensim.config import Paths


def _run(tmp_path, price, gen_overrides=None, fuel_available=None, n=8):
    ts = pd.date_range("2025-03-07 05:00", periods=n, freq="h", tz="UTC")  # = 00:00 EST
    df = pd.DataFrame({
        "timestamp": ts,
        "gas_price_effective": 4.0,           # 9000 Btu/kWh -> $36/MWh fuel
        "price_mwh": price if isinstance(price, list) else [price] * n,
        "permit_allowed": 1,
        "fuel_available": fuel_available or [1] * n,
        "ppa_active": 0, "event_active": 0, "export_cap_mw": 9999.0,
    })
    paths = Paths(tmp_path)
    df.to_csv(paths.merged_inputs, index=False)
    gen = {"name": "g", "heat_rate_btu_per_kwh": 9000, "capacity_mw": 2.0, "min_margin_threshold": 5.0,
           "vom_per_mwh": 0.0, "availability_cap": 1.0, "maintenance_windows": [],
           "ramp_to_full_minutes": 0, "ramp_rate_mw_per_hr": 0.0, "min_up_hours": 0, "min_down_hours": 0}
    gen.update(gen_overrides or {})
    cfg = {"generators": [gen], "operations": {"program_mode": "WHOLESALE", "export_mode": "full_export"}}
    return simulate(cfg, paths)


def test_threshold_is_strict(tmp_path):
    out = _run(tmp_path, price=41.0)  # margin exactly 5.0 == threshold -> do not run
    assert not out["g_run"].any()
    out = _run(tmp_path, price=41.01)
    assert out["g_run"].all()


def test_negative_margin_never_dispatched(tmp_path):
    out = _run(tmp_path, price=20.0)
    assert (out["g_output_mw"] == 0).all() and (out["g_profit"] == 0).all()


def test_maintenance_window_forces_off(tmp_path):
    w = [{"start": "2025-03-07 02:00", "end": "2025-03-07 05:00", "reason": "test (EST)"}]
    out = _run(tmp_path, price=80.0, gen_overrides={"maintenance_windows": w, "min_up_hours": 24})
    assert out["g_run"].tolist() == [True, True, False, False, False, True, True, True]


def test_hard_gate_overrides_min_up(tmp_path):
    fuel = [1, 1, 0, 0, 1, 1, 1, 1]
    out = _run(tmp_path, price=80.0, fuel_available=fuel, gen_overrides={"min_up_hours": 24})
    assert out["g_run"].tolist() == [bool(f) for f in fuel]


def test_availability_caps_output(tmp_path):
    out = _run(tmp_path, price=80.0, gen_overrides={"availability_cap": 0.9})
    assert out["g_output_mw"].max() == pytest.approx(1.8)
