"""20-year unlevered DCF for a run-of-river asset -> maximum acquisition price (= NPV).

Conventions (logged in ASSUMPTIONS.md):
  * annual calendar-year cash flows, end-of-year discounting from the valuation date;
  * generation = scenario annual MWh x fraction of the year in service (uniform within the year);
  * pre-tax unless asset.valuation.tax_rate > 0 (then simple tax on positive EBITDA, no depreciation);
  * no terminal value (the license term is unconfirmed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from gensim.revenue import pjm_capacity


@dataclass
class Case:
    regime: str = "as_operated"          # or "restored"
    annual_mwh: dict = field(default_factory=dict)   # {"as_operated": MWh, "restored": MWh} for the hydrology case
    capacity_scenario: str = "mid"
    energy_mult: float = 1.0             # sensitivities
    om_mult: float = 1.0
    reserve_mult: float = 1.0            # relicensing / dam-safety reserve
    label: str = ""


def _d(s) -> date:
    return date.fromisoformat(str(s))


def _fraction_after(year: int, start: date) -> tuple[float, float, float]:
    """Share of the year on/after `start`: (whole year, Jan-May part, Jun-Dec part)."""
    def share(a: date, b: date) -> float:
        lo = max(a, start)
        return max(0.0, (b - lo).days) / (b - a).days
    y0, y5, y12 = date(year, 1, 1), date(year, 6, 1), date(year + 1, 1, 1)
    return share(y0, y12), share(y0, y5), share(y5, y12)


def cash_flows(asset: dict, mkt: dict, case: Case) -> pd.DataFrame:
    v, costs, capex = asset["valuation"], asset["costs"], asset["capex"]
    y0 = _d(v["valuation_date"]).year
    years = list(range(y0, y0 + int(v["horizon_years"])))
    helene_rts = _d(capex["helene_repair"]["return_to_service"])
    restore_rts = _d(capex["restoration"]["return_to_service"])
    regimes = v["regimes"]
    elcc_class = asset["capacity_market"]["elcc_class"]
    contract = asset.get("contract", {})
    e_price0 = float(mkt["energy"]["placeholder_atc_price_mwh"]) * case.energy_mult
    e_esc = float(mkt["energy"]["escalation"])
    rec = float(mkt.get("recs", {}).get("price_mwh", 0.0))
    o_esc = float(costs["escalation"])

    rows = []
    for i, y in enumerate(years):
        f_on, f_on_a, f_on_b = _fraction_after(y, helene_rts)          # in service after Helene repair
        if case.regime == "restored":
            f_r, f_r_a, f_r_b = _fraction_after(y, restore_rts)
            f_r, f_r_a, f_r_b = min(f_r, f_on), min(f_r_a, f_on_a), min(f_r_b, f_on_b)
        else:
            f_r = f_r_a = f_r_b = 0.0
        f_ao, f_ao_a, f_ao_b = f_on - f_r, f_on_a - f_r_a, f_on_b - f_r_b   # as-operated share
        mwh = case.annual_mwh["as_operated"] * f_ao + case.annual_mwh["restored"] * f_r

        in_contract = contract.get("enabled") and y <= int(contract.get("end_year", 0))
        price = float(contract["fixed_price_mwh"]) if in_contract else e_price0 * (1 + e_esc) ** i
        energy = mwh * price
        recs = mwh * rec

        capacity = 0.0
        if not (in_contract and contract.get("capacity_sold_under_contract", False)):
            for reg, fa, fb in (("as_operated", f_ao_a, f_ao_b), ("restored", f_r_a, f_r_b)):
                if fa or fb:
                    capacity += pjm_capacity.calendar_year_revenue(
                        y, float(regimes[reg]["accredited_installed_mw"]), mkt, elcc_class,
                        case.capacity_scenario, (fa, fb))["net_usd"]

        esc = (1 + o_esc) ** i
        fixed_om = float(costs["fixed_om_per_kw_yr"]) * float(costs["om_basis_kw"]) * case.om_mult * esc
        other = sum(float(costs[k]) for k in ("insurance_per_yr", "property_tax_per_yr", "ferc_annual_charges_per_yr",
                                               "market_participant_fees_per_yr", "scada_monitoring_per_yr")) * esc
        opex = fixed_om + other

        cx = 0.0
        h = capex["helene_repair"]
        if int(h["spend_year"]) == y:
            cx += float(h["total_usd"]) * (1 - float(h["insured_fraction"]))
        if case.regime == "restored" and int(capex["restoration"]["spend_year"]) == y:
            cx += float(capex["restoration"]["total_usd"])
        cx += sum(float(it["usd"]) for it in capex.get("relicensing_dam_safety_reserve", []) if int(it["year"]) == y) * case.reserve_mult
        cx += sum(float(it["usd"]) for it in capex.get("major_overhauls", []) if int(it["year"]) == y)

        ebitda = energy + capacity + recs - opex
        tax = max(0.0, ebitda) * float(v.get("tax_rate", 0.0))
        rows.append({"year": y, "t": i + 1, "in_service": f_on, "restored_share": f_r, "mwh": mwh,
                     "energy_price": price, "energy_usd": energy, "capacity_usd": capacity, "rec_usd": recs,
                     "opex_usd": opex, "capex_usd": cx, "tax_usd": tax, "net_cf_usd": ebitda - tax - cx})
    return pd.DataFrame(rows)


def npv(cf: pd.DataFrame, rate: float) -> float:
    return float((cf["net_cf_usd"] / (1 + rate) ** cf["t"]).sum())


def irr(flows: list[float]) -> float:
    def f(r):
        return sum(c / (1 + r) ** k for k, c in enumerate(flows))
    try:
        return float(brentq(f, -0.99, 10.0))
    except ValueError:
        return float("nan")


def levered_equity_irr(cf: pd.DataFrame, price: float, debt_fraction: float, rate: float, tenor: int) -> dict:
    """Mortgage-style debt sized as a share of the purchase price; equity IRR at that price."""
    debt = price * debt_fraction
    pmt = debt * rate / (1 - (1 + rate) ** -tenor) if debt and rate else (debt / tenor if debt else 0.0)
    flows = [-(price - debt)]
    dscr = []
    for k, c in enumerate(cf["net_cf_usd"].tolist()):
        ds = pmt if k < tenor else 0.0
        flows.append(c - ds)
        if ds:
            dscr.append(c / ds)
    return {"equity_irr": irr(flows), "debt_usd": debt, "annual_debt_service": pmt,
            "min_dscr": float(np.min(dscr)) if dscr else float("nan")}
