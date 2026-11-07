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

## Capacity and valuation (2026-11-07)

- **BRA prices** as given (2026/27 329.17, 2027/28 333.44, 2028/29 325.00). **2029/30 is not cleared**
  (auction Dec 2026). Until it is, it is assumed equal to 2028/29 ($325, still under the collar)
  via `uncleared_collar_assumption`. After 2029/30: low/mid/high = 100/200/400 (placeholders).
- **ELCC Hydro Intermittent:** 35% (2028/29), 34% (2029/30). **Other years use the nearest listed
  year** (2026/27–2027/28 → 35%; 2030/31+ → 34%). Accredited MW = installed × rating; installed =
  5.0 MW net summer (restored) or 2.5 MW (as-operated regime cap).
- Delivery years (Jun–May) are blended into calendar years by days; out-of-service days earn no
  capacity revenue. Non-performance exposure is a 5% annual haircut (placeholder).
- **Energy is a placeholder** flat $45/MWh ATC, 2%/yr, until PJM DA LMPs are cached (needs
  PJM_API_KEY). It is the largest tornado driver, so treat all max-price numbers as provisional.
- DCF: annual calendar-year cash flows, end-of-year discounting from 2027-01-01, 20 years, pre-tax
  (tax_rate 0), **no terminal value** (license term unconfirmed). Generation in a year = scenario
  MWh × fraction of the year in service, spread evenly through the year (no seasonality).
- **Hydrology cases are 1-year exceedance levels held for all 20 years** (as the brief asks). That
  makes P90 a harsh downside: over 20 independent years the average sits near P50.
- **Regimes:** as-operated until the restoration return-to-service date, then restored output
  ("restored" case only), with restoration capex in its spend year. Helene repair: owner-borne
  share = total × (1 − insured fraction). Before Helene return to service: no output and no capacity
  revenue, but fixed costs continue.
- All cost and capex inputs in `config/assets/fries.yaml` marked PLACEHOLDER are illustrative,
  not researched values.

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

## Data sources (verified 2026-11-07)

- **USGS 03164000** daily mean discharge: 35,466 days, 1929-10-01 → 2026-11-06 (298 provisional).
  The OGC API (`/ogcapi/v1`; v0 forwards to it) and legacy NWIS dv agree on every day. The OGC
  API refuses to page when `sortby` is set, so results are sorted locally.
- **EIA-923** plant 10798 monthly net generation 2001-01 → 2026-08 (fuel2002=ALL, primeMover=ALL).
  2003–2016 mean = **26,081 MWh/yr** (published figure: 26,150). 2025-01 onward = 0 (Helene).
- **Observed step-down:** 2019 = 12.5 GWh, 2020 = 10.6 GWh, 2021–2024 ≈ 17.9–19.5 GWh/yr vs
  ≈ 26 GWh before. Cause unknown (unit(s) out? operating change under annual licenses?). This
  matters for valuation: "as operated recently" vs "restored to historical". **Status: open (Adam).**
- **EIA-860M (2026-08):** 4 units, all OP: GEN1 2.0, GEN2 0.8, GEN3 0.2, GEN4 2.4 MW nameplate
  (5.4 MW total); net summer 5.0 MW, winter 4.9 MW. Owner: Central Rivers Power US, LLC.
  Model cap uses **5.0 MW net summer**.

## FERC record — P-2883 (researched 2026-11-07)

- **FERC EA (Dec 2020)**: 41-ft dam; pool crest 2,188.27 ft, normal tailrace 2,148.50 ft, so gross
  head is **39.8 ft**. Units: mill house 2.0 + 0.8 + 0.25 MW (combined 1,250 cfs) and unit 4 2.1 MW
  Kaplan (800 cfs); total **2,050 cfs**; smallest unit minimum 60 cfs. Run-of-river within 0.2 ft;
  ~10 cfs leakage to the bypass; spill ~29% of the time. Mean flow 1,946 cfs. EA average generation 26,150 MWh/yr.
- **Relicensing risk:** Interior recommended bypass minimum flows at the 95% monthly exceedance level
  (455–1,133 cfs). FERC staff rejected this as not worth its **$185,350/yr** levelized cost. A future
  license or amendment could revive it; treat it as a downside scenario.
- **Cost priors (EA Table 6, 2020$, from the applicant):** O&M $484,010/yr (~$95/kW-yr),
  relicensing $348,840, net investment $904,200, dependable capacity 2.34 MW.
- **License: NEW LICENSE, not annual licenses.** FERC issued Aquenergy Systems, LLC a new license
  on **2022-01-20** (Order Issuing New License, 178 FERC ¶ 61,025, accession 20220120-3109; errata
  20220201-3106; Commissioner Danly concurred in part, dissented in part). Annual licenses covered only
  2020-06 → 2022-01. **The term and full operating articles are not yet retrieved**: the eLibrary file
  download needs a browser session. Known from secondary sources: run-of-river (Article 402); an
  article lets FERC require financial reserves; Interior's bypass min-flow 10(j) recommendation was
  not adopted (Danly's partial dissent). **Status: Adam to pull the order to confirm term, minimum-flow
  and fish-passage articles.**
- **Ownership/operator chain (eLibrary filings):** Enel Green Power North America (2019) → Central
  Rivers Power (2020–2022) → **Patriot Hydro, LLC** (2023+, filing "d/b/a" and "on behalf of" Aquenergy
  Systems, LLC, the licensee of record). EIA-860M still lists Central Rivers Power US, LLC.
- **eLibrary P-2883 since 2018 (500 filings reviewed by description):**
  - 2019-07 *penstock wall repair* calculations (CEII; not retrieved); 2019-08 powerhouse intake
    repair; certified 2020-07; final report accepted 2021-05. The concrete penstock feeds unit 4, which
    supports the unit-4-out hypothesis (see `docs/stepdown_diagnostic.md`).
  - Article 402 (run-of-river) deviations in 2023 and on 2024-09-05/06 (Helene); FERC did not treat
    them as violations.
  - Dam safety: hazard classification / inflow design flood work 2022–2024; **Spillway Capacity
    Assessment open** (FERC letter 2026-11-04); First Part 12D comprehensive assessment accepted
    2026-02. Feeds the dam-safety capex reserve.
  - **Helene repair:** power canal wall rehabilitation (roller-compacted concrete buttress). 100%
    design 2025-12; construction authorized **2026-02-11**; monthly construction reports from 2026-06;
    design change accepted for review 2026-09/10. Return to service: not stated; ongoing as of 2026-11.
  - **American Rivers moved to intervene (2026-07-15)**: reason not in the description. **Status: open.**
  - Recreation: RMP amended 2025-04; extension requested to 2028-12-31 for new facilities (license capex).
- **Contract status:** no Fries-specific QF Form 556 or PPA found by web search. FERC EQR was **not
  checked** (it needs the EQR download tool). **Status: open.**

## Hydrology / calibration

- **Hurricane Helene:** dam damaged Sept 2024 (>108,000 cfs over the spillway, per repair contractor);
  repairs underway. Sept 2024 onward = outage, excluded from calibration. Helene peak retained as a
  flood data point for the dam-safety reserve. Valuation gets two inputs: return-to-service date and
  repair/restoration capex (owner-borne vs insured split).
- **Exclusion rules are written before fitting and applied mechanically:** see
  `docs/calibration_protocol.md` (R1 Helene, R2 missing data, R3 above nameplate, R4 actual < 50% of
  the *prior-parameter* model at normal flow). Committed before the first fit.
- **EIA-923 monthly values 2001–2016 are imputed** (fractional MWh; EIA allocation of an annual
  filer's total). Fries reports monthly from 2017 (`Respondent Frequency = M` in 2020). Monthly
  tests against 2001–2016 are not meaningful. See `docs/calibration_v1_results.md`.
- **Protocol v2 (approved 2026-11-07):** annual fit 2003–2012 with availability = 1.0; validate
  2013–2018; monthly r on metered 2017–18; 2019–2023 = as-operated regime. **v2 also fails** annual
  ±5% (calibrate 6/10, validate 2/6) and monthly r (0.62); long-run +1.1% passes. See
  `docs/calibration_v2_results.md`. Q_minflow fit at its 100 cfs bound and H·η = 0.62 × gross are
  physically doubtful. The model probably lacks a head-vs-flow (tailwater) effect and unrecorded
  outages. **Status: results reported; next step is Adam's call.**
- **Valuation hydrology:** "restored" = v2 params (P50 26.5 GWh); "as operated" = regime params
  (P_cap ≈ 2.5 MW; P50 19.2 GWh). Both are in `docs/calibration_params.json`.
- **Holdout:** calibrate 2003–2012, validate 2013–2023 (minus excluded months). Report every year.

## Toolchain

- Python 3.14 with pandas 3.1.1 / numpy 2.5.4 wheels installs cleanly; no 3.12 fallback needed.
