"""Configuration, secrets and file locations.

Secrets come only from the environment / the repo-root .env (python-dotenv). Nothing secret is
ever read from or written to config files.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"
DEFAULT_CONFIG = CONFIG_DIR / "gas_genset.json"
DEFAULT_WORKDIR = Path(os.getenv("GENSIM_WORKDIR", REPO_ROOT / "outputs"))


_KEY_PARAM = re.compile(r"(api_key=)[^&\s'\"]+", re.IGNORECASE)


def redact(obj) -> str:
    """str(obj) with any api_key=... query value masked (requests errors embed the full URL)."""
    return _KEY_PARAM.sub(lambda m: m.group(1) + "***", str(obj))


class MissingSecret(RuntimeError):
    """A required key/contact is not set in the environment or .env."""


def load_env() -> None:
    # override=False: real environment variables win over .env
    load_dotenv(REPO_ROOT / ".env", override=False)


def _required_env(name: str, why: str) -> str:
    load_env()
    value = os.getenv(name, "").strip()
    if not value:
        raise MissingSecret(f"{name} is not set. Add it to .env (see .env.example). {why}".strip())
    return value


def eia_api_key() -> str:
    return _required_env("EIA_API_KEY", "")


def contact_email() -> str:
    return _required_env("GENSIM_CONTACT_EMAIL", "NWS requires a contact in User-Agent.")


def user_agent() -> str:
    return f"gen-sim/0.1 ({contact_email()})"


def load_config(path: Path | str = DEFAULT_CONFIG) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict, path: Path | str = DEFAULT_CONFIG) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


@dataclass(frozen=True)
class Paths:
    """On-disk locations of pipeline inputs/outputs inside one working directory.

    File names are the legacy ones so existing outputs stay readable.
    """

    workdir: Path

    def __post_init__(self):
        object.__setattr__(self, "workdir", Path(self.workdir))

    def _p(self, name: str) -> Path:
        return self.workdir / name

    @property
    def demand(self): return self._p("duke_demand.csv")
    @property
    def gas(self): return self._p("henry_hub_daily.csv")
    @property
    def weather_observed(self): return self._p("weather_observed.csv")
    @property
    def weather_forecast(self): return self._p("weather_forecast.csv")
    @property
    def merged_weather(self): return self._p("merged_weather.csv")
    @property
    def market_price(self): return self._p("market_price.csv")
    @property
    def merged_inputs(self): return self._p("merged_inputs.csv")
    @property
    def simulation_results(self): return self._p("simulation_results.csv")
    @property
    def last_updated(self): return self._p("last_updated.txt")
    # optional user-supplied series
    @property
    def site_load(self): return self._p("site_load.csv")
    @property
    def avoided_cost(self): return self._p("avoided_cost.csv")
    @property
    def fuel_curtailments(self): return self._p("fuel_curtailments.csv")
    @property
    def dr_events(self): return self._p("dr_events.csv")

    def ensure(self) -> "Paths":
        self.workdir.mkdir(parents=True, exist_ok=True)
        return self
