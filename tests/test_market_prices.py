"""Defects #1 and #2: no EIA 'price' fallback; demand-sized values are never rescaled into $/MWh."""
from pathlib import Path

import pandas as pd
import pytest

from gensim.config import Paths
from gensim.data import market_prices
from gensim.data.market_prices import NoPriceSource, normalize_prices_df

FIX = Path(__file__).parent / "fixtures" / "legacy"


def test_demand_sized_series_is_rejected_not_divided_by_100():
    # Legacy behavior: median > 1000 -> /100, which turned Duke demand (MW) into "$/MWh".
    raw = pd.read_csv(FIX / "raw_prices_large.csv")
    with pytest.raises(ValueError, match="looks like load in MW"):
        normalize_prices_df(raw)


def test_plausible_prices_pass_through_unscaled():
    raw = pd.DataFrame({"period": ["2025-03-08T22", "2025-03-08T23"], "value": [950.0, 30.0]})
    out = normalize_prices_df(raw)
    assert out["price_mwh"].tolist() == [950.0, 30.0]


@pytest.mark.parametrize("ba, hint", [("DUK", "avoided-cost"), ("PJM", "Data Miner 2"), ("TVA", "GENSIM_PRICE_FILE")])
def test_no_price_source_raises_with_guidance(ba, hint, tmp_path, monkeypatch):
    for v in ("GENSIM_PRICE_URL", "GENSIM_PRICE_FILE", "PJM_5MIN_URL", "PJM_5MIN_FILE"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(NoPriceSource, match=hint):
        market_prices.fetch_market_prices({"market": {"ba": ba}}, Paths(tmp_path))
    assert not (tmp_path / "market_price.csv").exists()


def test_module_has_no_eia_price_routes():
    src = Path(market_prices.__file__).read_text(encoding="utf-8")
    assert "api.eia.gov" not in src
    assert "\"EBA." not in src  # no EIA-930 series id literals


def test_user_price_file_is_loaded(tmp_path, monkeypatch):
    f = tmp_path / "prices_in.csv"
    pd.DataFrame({"datetime": ["2025-03-07 10:00", "2025-03-07 11:00"], "LMP": [41.5, 39.0]}).to_csv(f, index=False)
    monkeypatch.setenv("GENSIM_PRICE_FILE", str(f))
    out = market_prices.fetch_market_prices({"market": {"ba": "PJM"}}, Paths(tmp_path))
    assert out["price_mwh"].tolist() == [41.5, 39.0]
    assert (tmp_path / "market_price.csv").exists()
