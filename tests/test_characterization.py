"""Characterization (golden-master) tests.

Goldens were generated from the UNMODIFIED Original_GenSim code under pandas 2.3.3
(see tests/golden/README.md). They pin current behavior, bugs included, so refactors can be
proven behavior-neutral. A defect fix that changes outputs must update the affected goldens
in the same commit and say why in the commit message.

Regenerate:  GENSIM_UPDATE_GOLDEN=1 python -m pytest tests/test_characterization.py
"""
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from legacy_runner import run_normalize_prices, run_scenario

GOLDEN = Path(__file__).parent / "golden"
UPDATE = os.getenv("GENSIM_UPDATE_GOLDEN") == "1"
SCENARIOS = ["wholesale", "purpa"]


def _check(actual: Path, golden: Path) -> None:
    if UPDATE:
        golden.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(actual, golden)
        return
    assert golden.exists(), f"missing golden {golden}; run with GENSIM_UPDATE_GOLDEN=1"
    got = pd.read_csv(actual)
    want = pd.read_csv(golden)
    pd.testing.assert_frame_equal(got, want, check_exact=False, rtol=1e-9, atol=1e-9)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_pipeline_matches_golden(scenario, tmp_path):
    for name, path in run_scenario(scenario, tmp_path).items():
        _check(path, GOLDEN / scenario / f"{name}.csv")


def test_normalize_prices_matches_golden(tmp_path, monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "characterization-dummy-key")  # import-time check only; no network
    for name, path in run_normalize_prices(tmp_path).items():
        _check(path, GOLDEN / f"{name}.csv")
