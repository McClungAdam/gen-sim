"""Dashboard renders without exceptions on fixture outputs. No buttons clicked, no network."""
import shutil
from pathlib import Path

import pytest

import gensim.config

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "golden" / "wholesale"


def test_dashboard_renders(tmp_path, monkeypatch):
    for name in ("merged_inputs.csv", "simulation_results.csv", "merged_weather.csv"):
        shutil.copyfile(GOLDEN / name, tmp_path / name)
    (tmp_path / "last_updated.txt").write_text("2025-03-12 00:00:00")
    monkeypatch.setattr(gensim.config, "DEFAULT_WORKDIR", tmp_path)

    at = AppTest.from_file(str(REPO / "app" / "dashboard.py"), default_timeout=60).run()

    assert not at.exception, [e.value for e in at.exception]
    assert any("Generator Dispatch Simulator" in t.value for t in at.title)
