"""Adapter that runs the pipeline on the synthetic fixture and returns paths to its outputs.

This is the ONLY file that knows how the pipeline is invoked. The golden files under
tests/golden/ are the contract: restructuring may change this adapter, never the goldens.
(Goldens were produced via the pre-restructure legacy scripts; see tests/golden/README.md.)

The clock is frozen by passing `now` explicitly.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gensim import pipeline
from gensim.config import Paths
from gensim.data import weather
from gensim.data.market_prices import normalize_prices_df

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
INPUT_CSVS = [
    "duke_demand.csv",
    "market_price.csv",
    "henry_hub_daily.csv",
    "weather_observed.csv",
    "weather_forecast.csv",
]
RAW_PRICE_CASES = ["normal"]  # "large" (demand-like) must now raise: tests/test_market_prices.py

# "Now" for the frozen clock: just after the fixture window ends (naive local, as the legacy
# merge used datetime.now()); merge_weather compares against tz-aware UTC.
FROZEN_NOW = datetime(2025, 3, 12, 0, 0)
FROZEN_NOW_UTC = FROZEN_NOW.replace(tzinfo=timezone.utc)


def _stage(workdir: Path, csvs: list[str]) -> Paths:
    for name in csvs:
        shutil.copyfile(FIXTURES / "legacy" / name, workdir / name)
    return Paths(workdir)


def run_scenario(scenario: str, workdir: Path) -> dict[str, Path]:
    """merge_weather -> merge_inputs -> simulate on the fixture (no fetch, no network)."""
    paths = _stage(workdir, INPUT_CSVS)
    weather.merge_weather(paths, now=FROZEN_NOW_UTC)
    pipeline.run(FIXTURES / f"config_{scenario}.json", workdir, do_fetch=False, now=FROZEN_NOW)
    return {
        "merged_weather": paths.merged_weather,
        "merged_inputs": paths.merged_inputs,
        "simulation_results": paths.simulation_results,
    }


def run_normalize_prices(workdir: Path) -> dict[str, Path]:
    """normalize_prices_df on raw EIA-style frames (no network)."""
    _stage(workdir, [f"raw_prices_{c}.csv" for c in RAW_PRICE_CASES])
    outs = {}
    for case in RAW_PRICE_CASES:
        raw = pd.read_csv(workdir / f"raw_prices_{case}.csv")
        path = workdir / f"normalized_prices_{case}.csv"
        normalize_prices_df(raw).to_csv(path, index=False)
        outs[f"normalized_prices_{case}"] = path
    return outs
