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

## Secrets

- The same EIA key appeared in 6 legacy files (`get_demand.py`, `get_gas_prices.py`, `config.json`
  in both variants). None were copied; keys load from `.env` only. **Status: rotation pending (Adam).**
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
