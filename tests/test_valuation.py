"""DCF mechanics, regimes, contract toggle, levered case, scenario grid and tornado."""
import copy

import pytest

from gensim.revenue.pjm_capacity import load_market
from gensim.valuation import dcf, scenarios

HYD = {"P50": {"as_operated": 18000.0, "restored": 26000.0},
       "P90": {"as_operated": 15000.0, "restored": 19000.0},
       "P10": {"as_operated": 21000.0, "restored": 32000.0}}


@pytest.fixture
def asset():
    a = scenarios.load_asset()
    a = copy.deepcopy(a)
    a["valuation"]["valuation_date"] = "2027-01-01"
    a["capex"]["helene_repair"]["return_to_service"] = "2027-07-02"     # 183 of 365 days in service
    a["capex"]["restoration"]["return_to_service"] = "2028-01-01"
    return a


@pytest.fixture
def mkt():
    return load_market()


def test_npv_and_irr_basics():
    import pandas as pd
    cf = pd.DataFrame({"t": [1, 2], "net_cf_usd": [110.0, 121.0]})
    assert dcf.npv(cf, 0.10) == pytest.approx(200.0)
    assert dcf.irr([-100.0, 110.0]) == pytest.approx(0.10)


def test_return_to_service_prorates_generation(asset, mkt):
    cf = dcf.cash_flows(asset, mkt, dcf.Case(regime="as_operated", annual_mwh=HYD["P50"])).set_index("year")
    assert cf.loc[2027, "mwh"] == pytest.approx(18000 * 183 / 365)
    assert cf.loc[2028, "mwh"] == pytest.approx(18000)
    assert len(cf) == asset["valuation"]["horizon_years"]


def test_restored_regime_switches_output_and_spends_restoration(asset, mkt):
    ao = dcf.cash_flows(asset, mkt, dcf.Case(regime="as_operated", annual_mwh=HYD["P50"])).set_index("year")
    rs = dcf.cash_flows(asset, mkt, dcf.Case(regime="restored", annual_mwh=HYD["P50"])).set_index("year")
    assert rs.loc[2027, "mwh"] == pytest.approx(ao.loc[2027, "mwh"])           # restoration RTS 2028
    assert rs.loc[2029, "mwh"] == pytest.approx(26000)
    restoration = asset["capex"]["restoration"]["total_usd"]
    assert rs.loc[2027, "capex_usd"] - ao.loc[2027, "capex_usd"] == pytest.approx(restoration)
    assert rs.loc[2029, "capacity_usd"] > ao.loc[2029, "capacity_usd"]        # 5.0 vs 2.5 installed MW


def test_helene_owner_share_only(asset, mkt):
    cf = dcf.cash_flows(asset, mkt, dcf.Case(regime="as_operated", annual_mwh=HYD["P50"])).set_index("year")
    h = asset["capex"]["helene_repair"]
    assert cf.loc[int(h["spend_year"]), "capex_usd"] >= h["total_usd"] * (1 - h["insured_fraction"])


def test_contract_toggle(asset, mkt):
    asset["contract"].update(enabled=True, fixed_price_mwh=55.0, capacity_sold_under_contract=True, end_year=2030)
    cf = dcf.cash_flows(asset, mkt, dcf.Case(regime="as_operated", annual_mwh=HYD["P50"])).set_index("year")
    assert cf.loc[2029, "energy_price"] == 55.0 and cf.loc[2029, "capacity_usd"] == 0.0
    assert cf.loc[2031, "energy_price"] != 55.0 and cf.loc[2031, "capacity_usd"] > 0


def test_sensitivity_multipliers_move_npv_the_right_way(asset, mkt):
    base = dcf.Case(regime="as_operated", annual_mwh=HYD["P50"])
    v = lambda c: dcf.npv(dcf.cash_flows(asset, mkt, c), 0.10)
    from dataclasses import replace
    assert v(replace(base, energy_mult=1.3)) > v(base) > v(replace(base, energy_mult=0.7))
    assert v(replace(base, om_mult=0.75)) > v(base) > v(replace(base, om_mult=1.25))
    assert v(replace(base, reserve_mult=0.5)) > v(base) > v(replace(base, reserve_mult=1.5))


def test_levered_equity_irr(asset, mkt):
    cf = dcf.cash_flows(asset, mkt, dcf.Case(regime="as_operated", annual_mwh=HYD["P50"]))
    unlev = dcf.levered_equity_irr(cf, 1_000_000, 0.0, 0.07, 10)["equity_irr"]
    lev = dcf.levered_equity_irr(cf, 1_000_000, 0.5, 0.07, 10)
    assert lev["debt_usd"] == 500_000 and lev["annual_debt_service"] > 0
    assert lev["equity_irr"] != pytest.approx(unlev)


def test_grid_and_tornado(asset, mkt):
    g = scenarios.grid(asset, mkt, HYD)
    assert len(g) == 2 * 2 * 3 and {"max_price_8pct", "max_price_10pct", "max_price_12pct"} <= set(g.columns)
    p50 = g[(g.regime == "as_operated") & (g.hydrology == "P50")].set_index("capacity")["max_price_10pct"]
    assert p50["low"] < p50["mid"] < p50["high"]
    base, t = scenarios.tornado(asset, mkt, HYD)
    assert len(t) == 6 and (t["swing"] >= 0).all()
