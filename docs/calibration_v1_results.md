# Calibration v1 results (protocol as pre-registered in 56f44fe)

Run 2026-11-07 on USGS 03164000 (through 2026-11-06) and EIA-923 plant 10798 (through 2026-08).

## Fitted parameters

| Parameter | Fit | Prior | Note |
|---|---|---|---|
| H·η | 28.58 ft | 31.8 ft | 0.72 × gross head 39.77 ft |
| Q_max | 1,571 cfs | 2,050 cfs | below nameplate hydraulic capacity |
| Q_minflow | 0 cfs | 10 cfs | **at lower bound** |
| availability | 0.985 | — | collinear with H·η; effective scale H·η×avail = 28.15 ft |

## Acceptance

| Test | Calibrate 2003–12 | Validate 2013–23 | Result |
|---|---|---|---|
| Monthly r ≥ 0.9 | 0.67 (109 months) | 0.57 (99 months) | **fail** |
| Annual ±5%, unflagged years | 2 of 4 (2003 −9.9%, 2006 +7.5%) | 0 of 1 (2017 +8.7%) | **fail** |
| 2003–2016 modeled mean vs 26,150 | 26,621 MWh (+1.8%); EIA actual mean 26,081 | | pass |

Bias on used months: calibrate −1.4%, validate +18.4% (the 2019+ step-down).
Hydrology scenarios (water years 1930–2026, n = 97): P90 20,883 · P50 27,284 · P10 29,983 MWh/yr
(mean 26,235).

## Root cause of the monthly failure: EIA-923 monthly values for 2001–2016 are imputed

- Every month in 2001–2016 has fractional MWh (e.g. 2010-01 = 3,010.684). 2017 onward is integer.
- The 2020 bulk file lists Fries as `Respondent Frequency = M`. The 2010 file's values are fractional,
  consistent with EIA allocating an annual filer's total across months.
- So the **calibration window (2003–2012) has real annual totals but no real monthly data**.
  Monthly r there measures EIA's allocation method, not the model. R3 (above nameplate, e.g.
  2009-12 = 4,980 MWh > 5.4 MW × 744 h) and many R4 "outage" months before 2017 are probably
  allocation artifacts.
- Real monthly data exists only for 2017–2018 (pre step-down), 2019 (partly imputed), and 2020–2024
  (step-down period).

## Status

The protocol needs a decision before v2 (see the open question to Adam). The rules were **not**
changed after seeing these results.
