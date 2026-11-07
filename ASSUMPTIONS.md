# Assumptions & Decisions Log

Running log of assumptions, judgment calls and unverified facts. Each entry: what, why, status.

## Codebase baseline (2026-11-06)

- **Baseline = `Original_GenSim` (Aug 14, 2025)** for gas-genset dispatch logic (threshold, ramp,
  start cost, min up/down, availability, heat-rate conversion already correct there).
- **Ported from `Historical_gensim`:** EIA v2 pagination, `http_get` retry/backoff, fixed price-series
  selectbox index, dashboard Coverage Inspector. **Dropped:** `get_weather_history.py` (Meteostat),
  the library-style `merge_inputs`/`simulate_simple_margin` refactor (source of defects 3, 5, 6, 7).
- Step 1 defects 3, 5, 6, 7 exist only in `Historical_gensim`; defect 9a (`"\\n"` in
  `serialize_windows`) was not found in either variant. Original's dispatch ignores maintenance windows.
- **New defect #10 (found by characterization):** `merge_inputs._flag_windows` returns a
  timestamp-indexed Series that is assigned into a RangeIndex frame, so `fuel_available`,
  `event_active` and `ppa_active` are NaN whenever any window is configured. Effect: PURPA/DR modes
  never dispatch once a PPA/DR window exists; fuel curtailments are silently ignored.
- Original's daily gas forward-fill stops at the last daily print, so hours after it are NaN in
  `merged_inputs` (the simulator later ffills them). Treated as part of defect #5.
- Characterization goldens come from the unmodified Original code under pandas 2.3.3. A
  mechanical pandas-3 shim (`fillna(method=)`→`ffill/bfill`, `"H"`→`"h"`,
  `is_datetime64tz_dtype`→`isinstance(..., DatetimeTZDtype)`) reproduces them exactly under
  pandas 3.1.1. See `tests/golden/README.md`.
- The legacy merge window is relative to the clock (now − 45 days … now + 14 days). Stale cached
  data used to merge to 0 rows and crash the simulator; it now raises `MissingInput` ("No data
  overlaps the merge window"). `run_pipeline.py --as-of` sets "now" explicitly.
- **Column standard (defect #6):** Original's names are the standard (`demand_mw`, `price_mwh`,
  `gas_price`, `temp_f`/`condition`/`windSpeed`); Historical's `dry_bulb_c`/`wet_bulb_c`/`wind_mps`
  were never produced by any fetcher and are dropped. Required inputs: prices for WHOLESALE (and DR
  without a fixed DR rate); gas whenever gas units are configured. Demand and weather are optional
  and only informational.
- Fetch steps keep the legacy tolerance (one failing source doesn't stop the others; its cached
  file is used) but every failure is now reported. Printed request errors have `api_key=` redacted
  (requests' HTTPError messages embed the full URL).
- **Defect #2 verified (2026-11-06, with key):** EIA v2 `electricity/` has exactly six child routes
  (retail-sales, electric-power-operational-data, rto, state-electricity-profiles,
  operating-generator-capacity, facility-fuel); `electricity/wholesale-prices` returns 404.
  `facility-fuel` has monthly data 2001-01 → 2026-08 (calibration source).
- **Price inputs after the #1/#2 fix:** no EIA price fetch at all. PJM LMPs from Data Miner 2 (pending);
  DUK revenue only via explicit avoided cost; any other series via a user CSV (`GENSIM_PRICE_FILE`).
  Series with median > $1,000/MWh are rejected as "looks like MW", never rescaled.

## Timestamps (defect #4)

- Internal convention: tz-aware UTC; every file the pipeline writes carries `+00:00`. Naive
  timestamps in pipeline-written files raise instead of being guessed.
- Market zone per config `market.timezone`, default `America/New_York` (PJM EPT; Duke Eastern).
- Human inputs (maintenance/PPA/curtailment/DR windows, `--as-of`) are **market-local** time.
- EIA-930 hourly `period` values are UTC (EIA documentation).
- **Henry Hub daily price applies to the local calendar day** (midnight-to-midnight Eastern).
  Simplification: the NAESB gas day runs 9:00–9:00 Central. Immaterial for Phase 1 hydro.
- User price files: naive = `market.price_file_timezone` (default market zone); DST gaps raise.

## Secrets

- The same EIA key appeared in 6 legacy files (`get_demand.py`, `get_gas_prices.py`, `config.json`
  in both variants). None were copied into the repo; keys load from `.env` only.
  Key rotation deferred by owner; key confined to .env and the legacy folder.
- The GitHub remote's only prior commit (`c939325`, README) was scanned: no secrets.

## Market / contract status — Fries (EIA 10798, FERC P-2883)

- Treated as a **PJM merchant resource (base case)**. Evidence (from Adam): PJM queue position O31
  (5.21 MW, operational); third-party listing as non-regulated IPP with LMP node
  "FRIES 12 KV FRIESHYD". **Status: pnode name to be verified against the PJM pnode feed.**
- Contract status unknown. To check: FERC EQR filings for seller Central Rivers Power US, LLC;
  eLibrary for a Form 556 (QF). A "contracted" toggle (fixed $/MWh, capacity sold or not) will model
  an inherited PPA. **Status: open.**

## Hydrology / calibration

- **Hurricane Helene:** dam damaged Sept 2024 (>108,000 cfs over the spillway, per repair contractor);
  repairs underway. Sept 2024 onward = outage, excluded from calibration. Helene peak retained as a
  flood data point for the dam-safety reserve. Valuation gets two inputs: return-to-service date and
  repair/restoration capex (owner-borne vs insured split).
- **Exclusion rules are written before fitting and applied mechanically** (rules to be recorded here
  before the first fit).
- **Holdout:** calibrate 2003–2012, validate 2013–2023 (minus excluded months). Report every year.

## Toolchain

- Python 3.14 with pandas 3.1.1 / numpy 2.5.4 wheels installs cleanly; no 3.12 fallback needed.
