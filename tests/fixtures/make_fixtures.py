"""Generate the synthetic characterization fixture (stdlib only, fully deterministic).

No real API data. Shapes mimic what the legacy fetchers write to disk:
  duke_demand.csv       timestamp (naive, UTC hours as EIA-930 returns them), value (MW)
  market_price.csv      timestamp (naive), price_mwh
  henry_hub_daily.csv   date, price ($/MMBtu); weekdays only, like the EIA spot series
  weather_observed.csv  timestamp (tz-aware UTC, NWS obs at :51), temp_f, condition, windSpeed, temperatureUnit
  weather_forecast.csv  timestamp (tz-aware, -05:00), temp_f, temperatureUnit, windSpeed ("5 mph"), condition
  raw_prices_*.csv      raw EIA-style frames (period, value) for _normalize_prices_df

The window (2025-03-07 .. 2025-03-11) spans the US DST change on 2025-03-09 on purpose.
Forecast rows are dated 2099 so merge_weather_inputs' "future only" filter is clock-independent.

Run:  python tests/fixtures/make_fixtures.py
"""
import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "legacy"
START = datetime(2025, 3, 7, 0, 0)
HOURS = 5 * 24


def _write(name, header, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def demand():
    rows = []
    for h in range(HOURS):
        t = START + timedelta(hours=h)
        mw = 12000 + 2500 * math.sin(2 * math.pi * (t.hour - 9) / 24) + 40 * (h % 7)
        rows.append([t.strftime("%Y-%m-%d %H:%M:%S"), int(round(mw))])
    _write("duke_demand.csv", ["timestamp", "value"], rows)


def prices():
    # Starts 2h later and ends 4h earlier than demand (exercises window clipping),
    # has a 3-hour gap (exercises forward fill) and one negative hour.
    rows = []
    for h in range(2, HOURS - 4):
        if 50 <= h < 53:
            continue
        t = START + timedelta(hours=h)
        p = 38 + 22 * math.sin(2 * math.pi * (t.hour - 10) / 24) + 3 * ((h * 7) % 5)
        if h == 75:
            p = -12.5
        rows.append([t.strftime("%Y-%m-%d %H:%M:%S"), round(p, 2)])
    _write("market_price.csv", ["timestamp", "price_mwh"], rows)


def gas():
    rows = []
    d = datetime(2025, 3, 6)
    for i in range(6):
        day = d + timedelta(days=i)
        if day.weekday() >= 5:  # no weekend prints
            continue
        rows.append([day.strftime("%Y-%m-%d"), round(4.10 + 0.07 * i - 0.03 * (i % 2), 2)])
    _write("henry_hub_daily.csv", ["date", "price"], rows)


def weather():
    conds = ["Clear", "Partly Cloudy", "Cloudy", "Light Rain"]
    obs = []
    for h in range(HOURS):
        t = START + timedelta(hours=h, minutes=51)
        temp_c = 8 + 6 * math.sin(2 * math.pi * (t.hour - 14) / 24)
        obs.append([t.strftime("%Y-%m-%d %H:%M:%S+00:00"), round(temp_c * 9 / 5 + 32, 2),
                    conds[(h // 6) % 4], round(2 + (h % 5) * 0.9, 1), "F"])
    _write("weather_observed.csv", ["timestamp", "temp_f", "condition", "windSpeed", "temperatureUnit"], obs)

    fc = []
    for h in range(6):
        t = datetime(2099, 1, 1) + timedelta(hours=h)
        fc.append([t.strftime("%Y-%m-%dT%H:%M:%S-05:00"), 40 + h, "F", f"{5 + h} mph", "Sunny"])
    _write("weather_forecast.csv", ["timestamp", "temp_f", "temperatureUnit", "windSpeed", "condition"], fc)


def raw_prices():
    # EIA v2 style rows: period like "2025-03-09T06", value. Spans the DST gap (02:00 local missing).
    base = datetime(2025, 3, 8, 22)
    normal, cents = [], []
    for h in range(10):
        t = base + timedelta(hours=h)
        p = round(30 + 2.5 * h, 2)
        normal.append([t.strftime("%Y-%m-%dT%H"), p])
        cents.append([t.strftime("%Y-%m-%dT%H"), int(13000 + 450 * h)])  # demand-like magnitudes
    _write("raw_prices_normal.csv", ["period", "value"], normal)
    _write("raw_prices_large.csv", ["period", "value"], cents)


if __name__ == "__main__":
    demand(); prices(); gas(); weather(); raw_prices()
    print("fixtures written to", OUT)
