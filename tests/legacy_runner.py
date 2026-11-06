"""Adapter that runs the pipeline on the synthetic fixture and returns paths to its outputs.

This is the ONLY file that knows how the pipeline is invoked. The golden files under
tests/golden/ are the contract: restructuring may change this adapter, never the goldens.

The legacy scripts read/write fixed filenames in the current directory and call
datetime.now(), so we run them in a temp dir with the clock frozen.
"""
from __future__ import annotations

import importlib
import os
import runpy
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
INPUT_CSVS = [
    "duke_demand.csv",
    "market_price.csv",
    "henry_hub_daily.csv",
    "weather_observed.csv",
    "weather_forecast.csv",
]
RAW_PRICE_CASES = ["normal", "large"]

# "Now" for the frozen clock: just after the fixture window ends.
FROZEN_NOW = datetime(2025, 3, 12, 0, 0)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FROZEN_NOW
        return FROZEN_NOW.replace(tzinfo=timezone.utc).astimezone(tz)


@contextmanager
def _cwd(path: Path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _fresh_import(name: str):
    """Import a legacy module from scratch (they read config.json at import/run time)."""
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def _stage(workdir: Path, config_name: str, csvs: list[str]) -> None:
    for name in csvs:
        shutil.copyfile(FIXTURES / "legacy" / name, workdir / name)
    shutil.copyfile(FIXTURES / config_name, workdir / "config.json")


def run_scenario(scenario: str, workdir: Path) -> dict[str, Path]:
    """merge_weather_inputs -> merge_inputs -> simulate_generator on the fixture."""
    _stage(workdir, f"config_{scenario}.json", INPUT_CSVS)
    with _cwd(workdir):
        runpy.run_path(str(REPO / "merge_weather_inputs.py"), run_name="__main__")
        mi = _fresh_import("merge_inputs")
        mi.datetime = _FrozenDatetime
        mi.merge_inputs()
        sg = _fresh_import("simulate_generator")
        sg.datetime = _FrozenDatetime
        sg.main()
    return {
        "merged_weather": workdir / "merged_weather.csv",
        "merged_inputs": workdir / "merged_inputs.csv",
        "simulation_results": workdir / "simulation_results.csv",
    }


def run_normalize_prices(workdir: Path) -> dict[str, Path]:
    """get_market_prices._normalize_prices_df on raw EIA-style frames (no network)."""
    _stage(workdir, "config_wholesale.json", [f"raw_prices_{c}.csv" for c in RAW_PRICE_CASES])
    outs = {}
    with _cwd(workdir):
        gmp = _fresh_import("get_market_prices")
        for case in RAW_PRICE_CASES:
            raw = pd.read_csv(f"raw_prices_{case}.csv")
            out = gmp._normalize_prices_df(raw)
            path = workdir / f"normalized_prices_{case}.csv"
            out.to_csv(path, index=False)
            outs[f"normalized_prices_{case}"] = path
    return outs
