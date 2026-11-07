"""Market price input: a user-supplied price file only.

EIA does NOT publish hourly LMPs (verified 2026-11-06: electricity/wholesale-prices -> 404; the
EIA-930 EBA series ids the legacy fallback used are demand in MW). So:
  * PJM energy prices come from PJM Data Miner 2 (gensim.data.pjm, pending the API key).
  * Duke territory has no wholesale market; revenue there is an explicit avoided-cost input
    (operations.avoided_cost_fixed_per_mwh or avoided_cost.csv), never a fetched "price".
  * Any other hourly/sub-hourly price series can be supplied as a CSV (timestamp, price_mwh).
"""
from __future__ import annotations

import io
import os

import pandas as pd
import requests

from gensim.config import Paths
from gensim.timeutil import market_tz, series_to_utc

# Values this large are not plausible $/MWh medians; the legacy code silently divided them by 100,
# which turned EIA-930 demand (MW) into a fake price. Refuse instead.
IMPLAUSIBLE_PRICE_MEDIAN = 1000.0


class NoPriceSource(RuntimeError):
    """No price source is configured for this market."""


def normalize_prices_df(df: pd.DataFrame, assume_tz: str | None = "America/New_York") -> pd.DataFrame:
    """-> columns timestamp (tz-aware UTC), price_mwh.

    Offset-aware input is converted; naive input is market-local time `assume_tz` (defect #4: the
    legacy code labeled UTC data as New York and silently shifted the spring-forward hour).
    """
    if "timestamp" not in df.columns and "period" in df.columns:
        df = df.rename(columns={"period": "timestamp"})
    if "price_mwh" not in df.columns and "value" in df.columns:
        df = df.rename(columns={"value": "price_mwh"})
    if not {"timestamp", "price_mwh"}.issubset(df.columns):
        raise ValueError("Input must contain 'timestamp' and 'price_mwh' (or mappable columns).")
    df = df.copy()
    df["timestamp"] = series_to_utc(df["timestamp"], assume_tz)
    df["price_mwh"] = pd.to_numeric(df["price_mwh"], errors="coerce")
    med = df["price_mwh"].median()
    if pd.notna(med) and med > IMPLAUSIBLE_PRICE_MEDIAN:
        raise ValueError(
            f"Median 'price' is {med:,.0f}, not a plausible $/MWh. This looks like load in MW "
            "(e.g. an EIA-930 demand series), not a price. Refusing to rescale it."
        )
    out = df[["timestamp", "price_mwh"]].dropna(subset=["timestamp"]).sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    return out


def _read_user_price_file() -> pd.DataFrame:
    """CSV from GENSIM_PRICE_URL / GENSIM_PRICE_FILE (legacy names PJM_5MIN_URL / PJM_5MIN_FILE accepted)."""
    url = (os.getenv("GENSIM_PRICE_URL") or os.getenv("PJM_5MIN_URL") or "").strip()
    fpath = (os.getenv("GENSIM_PRICE_FILE") or os.getenv("PJM_5MIN_FILE") or "").strip()
    if url:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
    elif fpath and os.path.exists(fpath):
        df = pd.read_csv(fpath)
    else:
        return None
    cols_lower = {c.lower(): c for c in df.columns}
    ts_col = cols_lower.get("timestamp") or cols_lower.get("datetime") or cols_lower.get("datetime_utc") or cols_lower.get("date_utc")
    price_col = cols_lower.get("price_mwh") or cols_lower.get("lmp") or cols_lower.get("rt_lmp") or cols_lower.get("price")
    if not (ts_col and price_col):
        raise ValueError("Price CSV lacks recognizable timestamp/price columns")
    return df.rename(columns={ts_col: "timestamp", price_col: "price_mwh"})


def fetch_market_prices(cfg: dict, paths: Paths) -> pd.DataFrame:
    ba = cfg.get("market", {}).get("ba", "DUK")
    df = _read_user_price_file()
    if df is None:
        if ba.upper() == "DUK":
            hint = ("Duke has no wholesale market: use an avoided-cost input "
                    "(operations.avoided_cost_fixed_per_mwh or avoided_cost.csv) with a PURPA program mode.")
        elif ba.upper() == "PJM":
            hint = "PJM LMPs come from PJM Data Miner 2 (not yet wired; needs PJM_API_KEY)."
        else:
            hint = "Supply a price CSV via GENSIM_PRICE_FILE."
        raise NoPriceSource(f"No price source for BA={ba}. EIA publishes no hourly LMPs. {hint}")
    out = normalize_prices_df(df, assume_tz=cfg.get("market", {}).get("price_file_timezone", market_tz(cfg)))
    out.to_csv(paths.market_price, index=False)
    print(f"✅ Saved {paths.market_price.name} with {len(out)} rows for BA={ba} from user price file")
    return out
