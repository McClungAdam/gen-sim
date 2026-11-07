"""EIA-923 plant net generation (monthly) and EIA-860M generator capacity, cached to disk.

Routes (EIA API v2): electricity/facility-fuel (fuel2002=ALL, primeMover=ALL is the plant total)
and electricity/operating-generator-capacity.
"""
from __future__ import annotations

import os

import pandas as pd

from gensim.config import DATA_CACHE
from gensim.data.http import eia_v2_data


def _cache(name: str):
    p = DATA_CACHE / "eia"
    os.makedirs(p, exist_ok=True)
    return p / name


def monthly_generation(plant_id: int | str, *, refresh: bool = False, fetch=eia_v2_data) -> pd.DataFrame:
    """Columns: month (YYYY-MM), net_generation_mwh. Plant total across fuels and prime movers."""
    path = _cache(f"eia923_plant_{plant_id}_monthly.csv")
    if path.exists() and not refresh:
        return pd.read_csv(path, dtype={"month": str})
    rows = fetch("electricity/facility-fuel", frequency="monthly", data=["generation"],
                 facets={"plantCode": [str(plant_id)], "fuel2002": ["ALL"], "primeMover": ["ALL"]})
    if not rows:
        raise RuntimeError(f"EIA-923 returned no rows for plant {plant_id}")
    df = pd.DataFrame(rows)
    units = set(df.get("generation-units", pd.Series(["megawatthours"])).dropna())
    if units - {"megawatthours"}:
        raise ValueError(f"Unexpected EIA-923 generation units {units}")
    out = (pd.DataFrame({"month": df["period"].astype(str),
                         "net_generation_mwh": pd.to_numeric(df["generation"], errors="coerce")})
           .drop_duplicates("month", keep="last").sort_values("month").reset_index(drop=True))
    out.to_csv(path, index=False)
    print(f"✅ EIA-923 plant {plant_id}: {len(out)} months {out['month'].iloc[0]} → {out['month'].iloc[-1]}")
    return out


def generator_capacity(plant_id: int | str, *, start: str = "2024-01", fetch=eia_v2_data) -> pd.DataFrame:
    """Latest month's generators: generator_id, nameplate_mw, summer_mw, winter_mw, status, owner."""
    rows = fetch("electricity/operating-generator-capacity", frequency="monthly",
                 data=["nameplate-capacity-mw", "net-summer-capacity-mw", "net-winter-capacity-mw"],
                 facets={"plantid": [str(plant_id)]}, start=start)
    if not rows:
        raise RuntimeError(f"EIA-860M returned no generators for plant {plant_id}")
    df = pd.DataFrame(rows)
    latest = df[df["period"] == df["period"].max()]
    return pd.DataFrame({
        "period": latest["period"],
        "generator_id": latest["generatorid"],
        "nameplate_mw": pd.to_numeric(latest["nameplate-capacity-mw"], errors="coerce"),
        "summer_mw": pd.to_numeric(latest["net-summer-capacity-mw"], errors="coerce"),
        "winter_mw": pd.to_numeric(latest["net-winter-capacity-mw"], errors="coerce"),
        "status": latest.get("status"),
        "owner": latest.get("entityName"),
    }).sort_values("generator_id").reset_index(drop=True)
