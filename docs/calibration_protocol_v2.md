# Fries calibration protocol v2 (written before the v2 refit)

Supersedes `calibration_protocol.md` (v1) for fitting. v1 and its results
(`calibration_v1_results.md`) are kept unchanged as the record. Approved by Adam on 2026-11-07.

## Why v2

v1 fit and scored monthly data. EIA-923 monthly values for Fries in **2001–2016 are imputed**
(every month fractional: EIA allocates an annual filer's total across months). Fries reports monthly
from 2017. So the 2003–2012 window has real **annual** totals and no real monthly data. Monthly r
against it measured EIA's allocation method, and the v1 monthly R3/R4 exclusions before 2017 were
largely allocation artifacts.

Disclosure: the v1 run showed annual model-vs-actual numbers under v1 parameters before this
protocol was written. The annual rules below are mechanical translations of v1's R1–R4. Their
thresholds are unchanged and were not chosen by looking at which years they drop.

## Model

Same as v1 (`gensim/assets/hydro_ror.py`), with **availability fixed at 1.0**. It is collinear with
H·η, and 10 annual points cannot separate them; any real availability loss is absorbed into H·η.
`P_cap` = 5.0 MW.

Free parameters and bounds (unchanged from v1): H·η 0.60–0.92 × 39.77 ft; Q_max 1,500–2,300 cfs;
Q_minflow 0–100 cfs.

## Annual exclusion rules (calendar years; first matching rule wins)

- **A1 Known outage:** 2024 and later (Helene from 2024-09; 2024 is partial).
- **A2 Incomplete data:** fewer than 12 EIA months, or more than 10 USGS flow days missing in the year.
- **A3 Implausibly high:** annual actual > 5.4 MW × hours in year.
- **A4 Outage/derate screen:** annual actual < **0.50 ×** the *prior-parameter* (v1 PRIOR,
  availability 1.0) annual model **and** the year's mean flow is within the 5th–95th percentile of
  annual mean flows 1930–2023.

## Periods

- **Calibrate:** 2003–2012, unexcluded years. Objective: sum of squared annual errors (MWh).
- **Validate:** 2013–2018, unexcluded years, annual. Nothing from these years is used in fitting.
- **Monthly check:** metered months 2017-01 … 2018-12 only (EIA integer, monthly respondent).
- **As-operated regime:** 2019–2023, reported separately. **Not validation.** Diagnostics only
  (see `stepdown_diagnostic.md`).

## Acceptance

1. |annual error| ≤ 5% for every unexcluded year, in both calibration and validation.
2. Monthly r ≥ 0.9 on 2017–2018 metered months.
3. The modeled 2003–2016 mean is near 26,150 MWh/yr (report % difference).
