# Fries calibration protocol (written before any fit)

Committed before the first fit so the git history shows the rules were not tuned to the result.
Implemented mechanically in `gensim/calibration/rules.py`. Changing a rule after fitting needs a new
commit that says why, plus a report of both versions.

## Data

- **Flow:** USGS 03164000 New River near Galax, daily mean discharge (cfs). The drainage area
  (1,141 mi²) ≈ the dam's (1,140 mi²), so no area scaling.
- **Actual generation:** EIA-923 monthly net generation, plant 10798 (fuel2002=ALL, primeMover=ALL).
- **Unit of comparison:** calendar month.

## Model (daily step)

```
Q_usable = clamp(Q_gauge − Q_minflow, 0, Q_max)                      [cfs]
P_MW     = min(9.81 × Q_usable × 0.0283168 × (H·η) × 0.3048 / 1000, P_cap)
MWh_day  = P_MW × 24 × availability
```
`H·η` is net head × efficiency in feet (one combined parameter). `P_cap` = 5.0 MW (EIA-860M net
summer, 2026-08).

## Priors (FERC EA for P-2883, Dec 2020)

| Parameter | Prior | Fit bounds | Source |
|---|---|---|---|
| Gross head | 39.8 ft (pool 2,188.27 − tailrace 2,148.50) | — | EA §2.1.1 |
| `H·η` | 0.80 × 39.8 = 31.8 ft | 0.60–0.92 × 39.8 ft | head from the EA; η typical of old Francis/Kaplan units |
| `Q_max` | 2,050 cfs (mill units 1,250 + unit 4 800) | 1,500–2,300 cfs | EA §2.1.4 |
| `Q_minflow` | 10 cfs (spillway/canal leakage; no bypass minimum flow required) | 0–100 cfs | EA §2.1.4 |
| `availability` | 1.0 for the screen | 0.80–1.00 | — |

## Exclusion rules (applied in this order; a month is excluded at its first matching rule)

- **R1 Known outage:** 2024-09 and later (Hurricane Helene damage). Applies to every month regardless of data.
- **R2 Missing data:** the EIA value is missing, or more than 3 days of USGS flow are missing in the month.
- **R3 Implausibly high:** actual > nameplate 5.4 MW × hours in month, which means a data error.
- **R4 Outage/derate screen:** actual < **0.50 ×** the *prior-parameter* model **and** the month's mean
  flow lies within the 5th–95th percentile of mean flows for that calendar month (1930–2023). The
  flow-band condition stops droughts and floods being mistaken for outages. Because the screen uses
  the prior parameters rather than the fitted ones, the fit cannot change which months are excluded.

**Year flag:** a year with any month excluded by R1–R4 is *flagged*. The ±5% annual criterion is
evaluated only on unflagged years. **Every year is reported**, flagged or not, with its reason.

## Split

- **Calibrate:** 2003-01 … 2012-12, unexcluded months only.
- **Validate:** 2013-01 … 2023-12, unexcluded months only. No parameter sees validation data.
- The published 26,150 MWh/yr long-run check uses 2003–2016 modeled generation, with no exclusions.

## Fit

- Objective: minimize the sum of squared monthly errors (MWh) on calibration months.
- Bounded optimizer from the priors, with a multi-start grid over `Q_max` and `H·η`.
- `H·η` and `availability` are nearly collinear (both scale output whenever the capacity cap is not
  binding). Both are reported, and so is their product, the "effective scale".

## Acceptance (Phase 1 brief)

1. |annual error| ≤ 5% for each unflagged overlapping year, in both calibration and validation.
2. Monthly correlation r ≥ 0.9, reported separately for calibration and validation.
3. The modeled 2003–2016 mean is near 26,150 MWh/yr (report % difference).

## Pre-registered diagnostic (not an exclusion)

EIA-923 shows a step-down from 2019 (12.5, 10.6, then ~18 GWh/yr vs ~26 GWh before). R4 catches only
severe months. Months in 2019–2023 that pass R4 stay in validation, so validation bias for those
years is **expected and will be reported**, together with a rolling actual/modeled ratio. How to
value the asset given this ("as recently operated" vs "restored") is the owner's decision; this
protocol does not make it.
