"""Capacity math: price lookup, ELCC, accredited MW, DY-to-calendar blending, haircut."""
import pytest

from gensim.revenue import pjm_capacity as cap

MKT = {"capacity": {
    "bra_prices": {"2026/27": 329.17, "2027/28": 333.44, "2028/29": 325.00, "2029/30": None},
    "uncleared_collar_assumption": 325.0,
    "post_collar_scenarios": {"low": 100.0, "mid": 200.0, "high": 400.0},
    "elcc": {"hydro_intermittent": {"2028/29": 0.35, "2029/30": 0.34}},
    "nonperformance_haircut": 0.05}}


def test_price_sources():
    assert cap.bra_price(2027, MKT, "mid") == (333.44, "cleared")
    assert cap.bra_price(2029, MKT, "mid")[0] == 325.0                     # uncleared, collar assumption
    assert cap.bra_price(2030, MKT, "low")[0] == 100.0
    assert cap.bra_price(2031, MKT, "high")[0] == 400.0


def test_elcc_nearest_year():
    assert cap.elcc_rating(2028, MKT, "hydro_intermittent") == (0.35, "listed")
    r, src = cap.elcc_rating(2026, MKT, "hydro_intermittent")
    assert r == 0.35 and "nearest" in src
    assert cap.elcc_rating(2035, MKT, "hydro_intermittent")[0] == 0.34
    with pytest.raises(ValueError):
        cap.elcc_rating(2028, MKT, "nope")


def test_dy_revenue_hand_check():
    r = cap.dy_revenue(2028, 5.0, MKT, "hydro_intermittent", "mid")
    # 325 $/MW-day x (5.0 x 0.35 = 1.75 MW) x 365 days = 207,593.75; x 0.95 = 197,214.0625
    assert r["accredited_mw"] == pytest.approx(1.75)
    assert r["gross_usd"] == pytest.approx(207593.75)
    assert r["net_usd"] == pytest.approx(197214.0625)


def test_calendar_year_blends_two_delivery_years():
    y = cap.calendar_year_revenue(2029, 5.0, MKT, "hydro_intermittent", "mid")
    jan_may = 325.0 * 5 * 0.35 * 151 * 0.95          # DY 2028/29, Jan 1-May 31 2029 (151 days)
    jun_dec = 325.0 * 5 * 0.34 * 214 * 0.95          # DY 2029/30, Jun 1-Dec 31 2029 (214 days)
    assert y["net_usd"] == pytest.approx(jan_may + jun_dec)


def test_out_of_service_part_earns_nothing():
    y = cap.calendar_year_revenue(2029, 5.0, MKT, "hydro_intermittent", "mid", (0.0, 1.0))
    assert y["parts"][0]["net_usd_in_year"] == 0.0 and y["net_usd"] > 0
