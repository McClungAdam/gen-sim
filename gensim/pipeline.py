"""Single pipeline entry: fetch -> merge -> simulate (-> value, Phase 1 to come).

Used by run_pipeline.py (CLI) and app/dashboard.py. Fetch steps keep the legacy dashboard's
tolerance (one failing source does not stop the others; its cached file is used), but every
failure is reported. Merge and simulate errors propagate.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from gensim.assets.gas_genset import simulate
from gensim.config import DEFAULT_CONFIG, DEFAULT_WORKDIR, Paths, load_config, redact
from gensim.data import eia, market_prices, weather
from gensim.merge import merge_inputs

# Same order as the legacy "Refresh All Data" button.
FETCH_STEPS: list[tuple[str, Callable[[dict, Paths], object]]] = [
    ("demand", lambda cfg, p: eia.fetch_duk_demand(p)),
    ("gas", lambda cfg, p: eia.fetch_henry_hub(p)),
    ("weather_observed", lambda cfg, p: weather.fetch_observed(p)),
    ("weather_forecast", lambda cfg, p: weather.fetch_forecast(p)),
    ("merge_weather", lambda cfg, p: weather.merge_weather(p)),
    ("market_prices", lambda cfg, p: market_prices.fetch_market_prices(cfg, p)),
]


def fetch(cfg: dict, paths: Paths, only: list[str] | None = None) -> dict[str, str]:
    """Run fetch steps; returns {step: error message} for steps that failed."""
    errors: dict[str, str] = {}
    for name, step in FETCH_STEPS:
        if only and name not in only:
            continue
        try:
            step(cfg, paths)
        except Exception as e:  # keep going; report at the end
            errors[name] = f"{type(e).__name__}: {redact(e)}"
            print(f"⚠️ fetch step '{name}' failed: {errors[name]}")
    return errors


def run(
    config_path: Path | str = DEFAULT_CONFIG,
    workdir: Path | str = DEFAULT_WORKDIR,
    *,
    do_fetch: bool = True,
    do_merge: bool = True,
    do_simulate: bool = True,
    now: datetime | None = None,
) -> dict:
    cfg = load_config(config_path)
    paths = Paths(workdir).ensure()
    result: dict = {"paths": paths, "fetch_errors": {}}
    if do_fetch:
        result["fetch_errors"] = fetch(cfg, paths)
    if do_merge:
        result["merged_inputs"] = merge_inputs(cfg, paths, now=now)
    if do_simulate:
        result["simulation_results"] = simulate(cfg, paths, now=now)
    return result


# ================================================================ merchant asset screen (Phase 1)
ASSET_STAGES = ("fetch", "calibrate", "value")


def run_asset(name: str = "fries", *, stages=ASSET_STAGES, refresh: bool = False,
              workdir: Path | str = DEFAULT_WORKDIR) -> dict:
    """fetch (USGS + EIA-923, cached) -> calibrate (docs/*.md + calibration_params.json) -> value."""
    from gensim.calibration import report
    from gensim.data import eia923, usgs
    from gensim.valuation import scenarios

    asset = scenarios.load_asset(name)
    out = Path(workdir) / name
    out.mkdir(parents=True, exist_ok=True)
    result: dict = {"outputs": out}
    flow = actual = None
    if "fetch" in stages or "calibrate" in stages:
        flow = usgs.daily_discharge(asset["hydro"]["usgs_site"], refresh=refresh and "fetch" in stages)
        actual = eia923.monthly_generation(asset["ids"]["eia_plant"], refresh=refresh and "fetch" in stages)
    if "calibrate" in stages:
        report.write(report.build(flow, actual))
        result["calibration"] = "docs/calibration_v2_results.md, docs/stepdown_diagnostic.md"
    if "value" in stages:
        g = scenarios.grid(asset)
        base, t = scenarios.tornado(asset)
        g.to_csv(out / "valuation_grid.csv", index=False)
        t.to_csv(out / "tornado.csv", index=False)
        result.update(grid=g, tornado=t, base_npv=base)
        print(f"✅ {name}: valuation grid ({len(g)} cases) and tornado written to {out}; base max price {base:,.0f}")
    return result
