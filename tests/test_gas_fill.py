"""Defect #5: daily gas covers each local day, carries over weekends, never invents fuel prices."""
import pandas as pd
import pytest

from gensim.assets.gas_genset import simulate
from gensim.config import Paths
from gensim.merge import _gas_on_timeline
from gensim.timeutil import dates_to_utc_day_start

NY = "America/New_York"


def _gas(dates, prices):
    return pd.DataFrame({"timestamp": dates_to_utc_day_start(dates, NY), "gas_price": prices})


def test_every_hour_of_the_day_gets_that_days_print():
    tl = pd.Series(pd.date_range("2025-03-07 05:00", periods=24, freq="h", tz="UTC"))  # Fri 00:00-23:00 EST
    s = _gas(["2025-03-07"], [4.2]).pipe(_gas_on_timeline, tl)
    assert s.notna().all() and (s == 4.2).all()


def test_last_day_is_filled_to_its_end():
    # Legacy: hours after the start of the last print were NaN.
    tl = pd.Series(pd.date_range("2025-03-11 04:00", periods=20, freq="h", tz="UTC"))
    s = _gas(["2025-03-10", "2025-03-11"], [4.0, 4.5]).pipe(_gas_on_timeline, tl)
    assert (s == 4.5).all()


def test_weekend_carries_friday_print():
    # Sat+Sun local = 47 h (DST starts Sunday); hour 48 is already Monday 00:00 EDT
    tl = pd.Series(pd.date_range("2025-03-08 05:00", periods=48, freq="h", tz="UTC"))
    s = _gas(["2025-03-07", "2025-03-10"], [4.1, 4.3]).pipe(_gas_on_timeline, tl)
    assert (s.iloc[:47] == 4.1).all() and s.iloc[47] == 4.3


def test_stale_beyond_carry_limit_is_nan():
    tl = pd.Series(pd.date_range("2025-03-12 04:00", periods=3, freq="h", tz="UTC"))  # 5 days after Fri
    s = _gas(["2025-03-07"], [4.1]).pipe(_gas_on_timeline, tl)
    assert s.isna().all()


def test_hours_before_first_print_are_nan_not_backfilled():
    tl = pd.Series(pd.date_range("2025-03-07 00:00", periods=6, freq="h", tz="UTC"))  # still Mar 6 in NY
    s = _gas(["2025-03-07"], [4.1]).pipe(_gas_on_timeline, tl)
    assert s.iloc[:5].isna().all() and s.iloc[5] == 4.1


def test_simulator_refuses_missing_gas(tmp_path):
    ts = pd.date_range("2025-03-07 05:00", periods=3, freq="h", tz="UTC")
    pd.DataFrame({"timestamp": ts, "gas_price_effective": [4.0, None, 4.0], "price_mwh": 80.0,
                  "permit_allowed": 1, "fuel_available": 1, "ppa_active": 0, "event_active": 0,
                  "export_cap_mw": 9999.0}).to_csv(Paths(tmp_path).merged_inputs, index=False)
    cfg = {"generators": [{"name": "g", "heat_rate_btu_per_kwh": 9000, "capacity_mw": 1.0, "min_margin_threshold": 0}],
           "operations": {"program_mode": "WHOLESALE"}}
    with pytest.raises(ValueError, match="gas price missing for 1 of 3"):
        simulate(cfg, Paths(tmp_path))
