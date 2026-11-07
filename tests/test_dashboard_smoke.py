"""Dashboard: renders on fixture outputs and the defect #9 fixes hold. No network, repo config untouched."""
import json
import shutil
from pathlib import Path

import pytest

import gensim.config
from gensim import pipeline
from gensim.windows import parse_windows_text, serialize_windows_text

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "golden" / "wholesale"


@pytest.fixture
def app(tmp_path, monkeypatch):
    for name in ("merged_inputs.csv", "simulation_results.csv", "merged_weather.csv"):
        shutil.copyfile(GOLDEN / name, tmp_path / name)
    (tmp_path / "last_updated.txt").write_text("2025-03-12 00:00:00")
    cfg_path = tmp_path / "config.json"
    shutil.copyfile(REPO / "tests" / "fixtures" / "config_wholesale.json", cfg_path)
    monkeypatch.setattr(gensim.config, "DEFAULT_WORKDIR", tmp_path)
    monkeypatch.setattr(gensim.config, "DEFAULT_CONFIG", cfg_path)
    calls = []
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: calls.append(k) or {"fetch_errors": {}})
    at = AppTest.from_file(str(REPO / "app" / "dashboard.py"), default_timeout=60).run()
    return at, cfg_path, calls


def test_dashboard_renders(app):
    at, _, _ = app
    assert not at.exception, [e.value for e in at.exception]
    assert any("Generator Dispatch Simulator" in t.value for t in at.title)
    assert any("Coverage Inspector" in s.value for s in at.subheader)


def test_9a_windows_round_trip():
    wins = [{"start": "2025-03-10 08:00", "end": "2025-03-10 16:00", "reason": "annual, borescope"},
            {"start": "2025-04-01 00:00", "end": "2025-04-02 00:00", "reason": ""}]
    text = serialize_windows_text(wins)
    assert text.count(chr(10)) == 1                 # one real newline between the two windows
    assert (chr(92) + "n") not in text              # no literal backslash-n (the suspected 9a bug)
    assert parse_windows_text(text) == wins


def test_9b_run_after_save_fires_on_submit(app):
    at, cfg_path, calls = app
    at.checkbox(key="gen_1_run_after_save").check()
    next(b for b in at.button if "Save GEN_1" in b.label).click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert calls == [{"do_fetch": False, "do_merge": False}]
    assert json.loads(cfg_path.read_text())["generators"][0]["name"] == "gen_1"


def test_9c_price_series_index_uses_series_options(app):
    at, _, _ = app
    sel = next(s for s in at.selectbox if s.label == "Price Series")
    assert sel.value == "DA" and sel.options == ["DA", "RT"]


def test_9d_negative_gas_basis_allowed(app):
    at, cfg_path, _ = app
    basis = next(n for n in at.number_input if n.label.startswith("Gas Basis"))
    basis.set_value(-0.45)
    next(b for b in at.button if "Save Market Settings" in b.label).click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert json.loads(cfg_path.read_text())["gas"]["basis_adder_per_mmbtu"] == pytest.approx(-0.45)
