"""PJM capacity revenue: BRA price x accredited MW (installed x ELCC class rating), by delivery year.

Delivery year (DY) "Y/Y+1" runs June 1 of Y to May 31 of Y+1. Calendar-year revenue blends two DYs
by days. Non-performance exposure is an annual haircut on capacity revenue (not ignored).
"""
from __future__ import annotations

from datetime import date

import yaml

from gensim.config import CONFIG_DIR


def load_market(path=CONFIG_DIR / "market.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def dy_label(start_year: int) -> str:
    return f"{start_year}/{str(start_year + 1)[-2:]}"


def _start(label: str) -> int:
    return int(label.split("/")[0])


def bra_price(start_year: int, mkt: dict, scenario: str) -> tuple[float, str]:
    """$/MW-day for the DY starting `start_year`, and where it came from."""
    cap = mkt["capacity"]
    prices = cap["bra_prices"]
    lab = dy_label(start_year)
    last_listed = max(_start(k) for k in prices)
    if lab in prices and prices[lab] is not None:
        return float(prices[lab]), "cleared"
    if lab in prices:                                            # listed but not cleared yet
        return float(cap["uncleared_collar_assumption"]), "uncleared (collar assumption)"
    if start_year > last_listed:
        return float(cap["post_collar_scenarios"][scenario]), f"post-collar scenario '{scenario}'"
    first_cleared = min(_start(k) for k, v in prices.items() if v is not None)
    return float(prices[dy_label(first_cleared)]), "before first listed DY (held at first cleared)"


def elcc_rating(start_year: int, mkt: dict, elcc_class: str) -> tuple[float, str]:
    table = mkt["capacity"]["elcc"].get(elcc_class) or {}
    if not table:
        raise ValueError(f"No ELCC ratings configured for class '{elcc_class}'")
    lab = dy_label(start_year)
    if lab in table:
        return float(table[lab]), "listed"
    nearest = min(table, key=lambda k: abs(_start(k) - start_year))
    return float(table[nearest]), f"nearest listed ({nearest})"


def accredited_mw(installed_mw: float, rating: float) -> float:
    return installed_mw * rating


def dy_revenue(start_year: int, installed_mw: float, mkt: dict, elcc_class: str, scenario: str) -> dict:
    price, psrc = bra_price(start_year, mkt, scenario)
    rating, rsrc = elcc_rating(start_year, mkt, elcc_class)
    days = (date(start_year + 1, 6, 1) - date(start_year, 6, 1)).days
    ucap = accredited_mw(installed_mw, rating)
    gross = price * ucap * days
    hair = float(mkt["capacity"].get("nonperformance_haircut", 0.0))
    return {"dy": dy_label(start_year), "price_mw_day": price, "price_source": psrc, "elcc": rating,
            "elcc_source": rsrc, "accredited_mw": ucap, "days": days, "gross_usd": gross,
            "haircut": hair, "net_usd": gross * (1 - hair)}


def calendar_year_revenue(year: int, installed_mw: float, mkt: dict, elcc_class: str, scenario: str,
                          in_service_fraction_by_part: tuple[float, float] = (1.0, 1.0)) -> dict:
    """Jan 1-May 31 belongs to DY (year-1), Jun 1-Dec 31 to DY (year). Pro-rated by days.

    in_service_fraction_by_part: share of each part during which the unit can deliver capacity
    (e.g. 0 while out of service for Helene repairs).
    """
    parts = []
    for dy_start, (a, b), f in ((year - 1, (date(year, 1, 1), date(year, 6, 1)), in_service_fraction_by_part[0]),
                                (year, (date(year, 6, 1), date(year + 1, 1, 1)), in_service_fraction_by_part[1])):
        r = dy_revenue(dy_start, installed_mw, mkt, elcc_class, scenario)
        d = (b - a).days
        parts.append({**r, "days_in_year": d, "in_service_fraction": f,
                      "net_usd_in_year": r["net_usd"] * d / r["days"] * f})
    return {"year": year, "net_usd": sum(p["net_usd_in_year"] for p in parts), "parts": parts}
