"""Defect #6: standard column names, explicit aliases, loud failures instead of silent drops."""
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from gensim.config import Paths, load_config
from gensim.merge import MissingInput, merge_inputs

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2025, 3, 12, 0, 0)


@pytest.fixture
def work(tmp_path):
    for f in ["duke_demand.csv", "market_price.csv", "henry_hub_daily.csv"]:
        shutil.copyfile(FIX / "legacy" / f, tmp_path / f)
    shutil.copyfile(Path(__file__).parent / "golden" / "wholesale" / "merged_weather.csv", tmp_path / "merged_weather.csv")
    return Paths(tmp_path)


def _cfg(mode="WHOLESALE"):
    cfg = load_config(FIX / "config_wholesale.json")
    cfg["operations"]["program_mode"] = mode
    return cfg


def test_standard_and_legacy_names_give_same_result(work):
    a = merge_inputs(_cfg(), work, now=NOW)
    d = pd.read_csv(work.demand).rename(columns={"value": "demand_mw"})
    d.to_csv(work.demand, index=False)
    g = pd.read_csv(work.gas).rename(columns={"price": "gas_price"})
    g.to_csv(work.gas, index=False)
    b = merge_inputs(_cfg(), work, now=NOW)
    pd.testing.assert_frame_equal(a, b)


def test_missing_required_column_raises(work):
    pd.read_csv(work.market_price).rename(columns={"price_mwh": "lmp_typo"}).to_csv(work.market_price, index=False)
    with pytest.raises(MissingInput, match=r"prices: market_price.csv lacks required column\(s\) \['price_mwh'\]"):
        merge_inputs(_cfg(), work, now=NOW)


def test_wholesale_without_prices_raises(work):
    work.market_price.unlink()
    with pytest.raises(MissingInput, match="prices: required input"):
        merge_inputs(_cfg(), work, now=NOW)


def test_purpa_without_prices_is_fine(work):
    work.market_price.unlink()
    out = merge_inputs(_cfg("PURPA"), work, now=NOW)
    assert out["price_mwh"].isna().all() and len(out) > 0


def test_gas_units_without_gas_raise(work):
    work.gas.unlink()
    with pytest.raises(MissingInput, match="gas: required input"):
        merge_inputs(_cfg(), work, now=NOW)


def test_unreadable_file_raises(work):
    work.demand.write_bytes(b"\x00\xff\x00 not,a\ncsv\x00\"")
    with pytest.raises(MissingInput):
        merge_inputs(_cfg(), work, now=NOW)


def test_blank_optional_cell_does_not_drop_the_row(work):
    w = pd.read_csv(work.merged_weather)
    w.loc[10, "condition"] = None
    w.to_csv(work.merged_weather, index=False)
    out = merge_inputs(_cfg(), work, now=NOW)
    assert out["temp_f"].notna().sum() == len(out)


def test_empty_window_is_a_clear_error(work):
    with pytest.raises(MissingInput, match="No data overlaps the merge window"):
        merge_inputs(_cfg(), work, now=datetime(2026, 11, 7))
