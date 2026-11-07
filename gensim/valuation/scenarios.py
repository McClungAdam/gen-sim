"""Scenario grid (max acquisition price) and tornado sensitivities.

Hydrology cases are single-year exceedance levels from the calibration (docs/calibration_params.json)
applied to every year. A 1-year P90 held for 20 years is a harsh downside; the 20-year average of
independent years would sit much closer to P50 (see ASSUMPTIONS.md).
"""
from __future__ import annotations

import json
from dataclasses import replace
from itertools import product

import pandas as pd
import yaml

from gensim.config import CONFIG_DIR, REPO_ROOT
from gensim.revenue.pjm_capacity import load_market
from gensim.valuation.dcf import Case, cash_flows, npv

PARAMS_JSON = REPO_ROOT / "docs" / "calibration_params.json"
HYDRO_KEYS = {"P90": "P90_mwh", "P50": "P50_mwh", "P10": "P10_mwh"}


def load_asset(name: str = "fries") -> dict:
    with open(CONFIG_DIR / "assets" / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def hydrology(path=PARAMS_JSON) -> dict:
    """{'P50': {'as_operated': MWh, 'restored': MWh}, ...}"""
    j = json.loads(open(path, encoding="utf-8").read())
    return {h: {"as_operated": j["exceedance_as_operated"][k], "restored": j["exceedance_restored"][k]}
            for h, k in HYDRO_KEYS.items()}


def grid(asset: dict | None = None, mkt: dict | None = None, hydro: dict | None = None,
         regimes=("as_operated", "restored"), hydros=("P50", "P90"), caps=("low", "mid", "high")) -> pd.DataFrame:
    asset, mkt, hydro = asset or load_asset(), mkt or load_market(), hydro or hydrology()
    rates = asset["valuation"]["discount_rates"]
    rows = []
    for reg, h, c in product(regimes, hydros, caps):
        cf = cash_flows(asset, mkt, Case(regime=reg, annual_mwh=hydro[h], capacity_scenario=c))
        row = {"regime": reg, "hydrology": h, "capacity": c,
               "avg_mwh": cf["mwh"].mean(), "yr1_net_cf": cf["net_cf_usd"].iloc[0]}
        row.update({f"max_price_{int(r * 100)}pct": npv(cf, r) for r in rates})
        rows.append(row)
    return pd.DataFrame(rows)


def tornado(asset: dict | None = None, mkt: dict | None = None, hydro: dict | None = None) -> tuple[float, pd.DataFrame]:
    """Base = asset.valuation.base_case. Returns (base NPV, rows of low/high NPV per driver)."""
    asset, mkt, hydro = asset or load_asset(), mkt or load_market(), hydro or hydrology()
    b = asset["valuation"]["base_case"]
    rate = float(b["discount_rate"])
    base = Case(regime=b["regime"], annual_mwh=hydro[b["hydrology"]], capacity_scenario=b["capacity"])

    def val(case):
        return npv(cash_flows(asset, mkt, case), rate)

    base_npv = val(base)
    drivers = [
        ("Energy price ±30%", replace(base, energy_mult=0.7), replace(base, energy_mult=1.3)),
        ("Capacity scenario low / high", replace(base, capacity_scenario="low"), replace(base, capacity_scenario="high")),
        ("Hydrology P90 / P10", replace(base, annual_mwh=hydro["P90"]), replace(base, annual_mwh=hydro["P10"])),
        ("O&M +25% / −25%", replace(base, om_mult=1.25), replace(base, om_mult=0.75)),
        ("Relicensing capex +50% / −50%", replace(base, reserve_mult=1.5), replace(base, reserve_mult=0.5)),
        ("Regime as-operated / restored", replace(base, regime="as_operated"), replace(base, regime="restored")),
    ]
    rows = [{"driver": d, "low_npv": val(lo), "high_npv": val(hi)} for d, lo, hi in drivers]
    t = pd.DataFrame(rows)
    t["swing"] = (t["high_npv"] - t["low_npv"]).abs()
    return base_npv, t.sort_values("swing", ascending=False).reset_index(drop=True)
