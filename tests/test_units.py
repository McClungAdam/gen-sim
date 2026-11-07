"""Defect #7: heat rate units converted in exactly one place."""
import pandas as pd
import pytest

from gensim.units import fuel_cost_per_mwh, heat_rate_mmbtu_per_mwh


def test_btu_per_kwh_to_mmbtu_per_mwh():
    assert heat_rate_mmbtu_per_mwh(9000) == pytest.approx(9.0)
    assert heat_rate_mmbtu_per_mwh(10500.0) == pytest.approx(10.5)


@pytest.mark.parametrize("bad", [9.0, 10.5, 0, 50000])
def test_rejects_wrong_units(bad):
    with pytest.raises(ValueError, match="Btu/kWh"):
        heat_rate_mmbtu_per_mwh(bad)


def test_fuel_cost_series():
    gas = pd.Series([3.0, 4.0])
    assert fuel_cost_per_mwh(9000, gas).tolist() == pytest.approx([27.0, 36.0])
