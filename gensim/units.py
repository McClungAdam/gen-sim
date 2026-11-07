"""Unit conversions. Each conversion lives in exactly one place."""


def heat_rate_mmbtu_per_mwh(btu_per_kwh: float) -> float:
    """Btu/kWh (config convention, e.g. 9000) -> MMBtu/MWh (e.g. 9.0).

    1 Btu/kWh = 1e-6 MMBtu / 1e-3 MWh = 1e-3 MMBtu/MWh.
    Rejects values that look like they are already MMBtu/MWh (real heat rates are ~6,000-15,000 Btu/kWh).
    """
    hr = float(btu_per_kwh)
    if not 1000.0 <= hr <= 30000.0:
        raise ValueError(
            f"heat_rate_btu_per_kwh={hr} is outside 1,000-30,000 Btu/kWh. "
            "If you entered MMBtu/MWh (e.g. 9.0), enter Btu/kWh (e.g. 9000) instead."
        )
    return hr / 1000.0


def fuel_cost_per_mwh(btu_per_kwh: float, gas_price_per_mmbtu):
    """$/MWh = MMBtu/MWh x $/MMBtu. Works on scalars or pandas Series."""
    return heat_rate_mmbtu_per_mwh(btu_per_kwh) * gas_price_per_mmbtu
