# 2019–2023 step-down diagnostic ("as-operated" regime)

Hypothesis (Adam, 2026-11-07): unit 4 (2.1 MW Kaplan, 800 cfs) out of service.
Method: hold the v2 H·η (24.69 ft) and Q_minflow (100 cfs) fixed and refit Q_max
and P_cap on 2021–2023. The test as specified uses annual data (3 points); a supplementary fit on the
36 metered monthly values for 2021–2023 is shown alongside.

## Regime fit

| Data | Q_max (cfs) | P_cap (MW) | RMSE (MWh) |
|---|---|---|---|
| Annual 2021–23 (as specified) | 1,536 | 2.46 | 912 per year |
| Monthly metered 2021–23 (supplementary) | 1,536 | 2.46 | 222 per month |

**The binding limit is identified; which limit binds is not.** The best fit caps output at ≈ 2.5 MW.
Almost equally good: Q_max ≈ 1,200 cfs with any cap ≥ 3 MW (at the fitted head, 1,200 cfs ≈ 2.5 MW).
Both describe a plant limited to about 2.5 MW / 1,200 cfs, the mill units' rating (1,250 cfs).
Error surface (RMSE, MWh/yr):

| q_max_cfs | P_cap 1.5 MW | P_cap 2.0 MW | P_cap 2.5 MW | P_cap 3.0 MW | P_cap 3.5 MW | P_cap 5.0 MW |
|---|---|---|---|---|---|---|
| 400 | 11,287 | 11,287 | 11,287 | 11,287 | 11,287 | 11,287 |
| 800 | 5,934 | 4,750 | 4,750 | 4,750 | 4,750 | 4,750 |
| 1200 | 5,934 | 2,749 | 930 | 940 | 940 | 940 |
| 1600 | 5,934 | 2,749 | 930 | 2,624 | 3,886 | 3,886 |
| 2000 | 5,934 | 2,749 | 930 | 2,624 | 4,395 | 6,193 |

## Named hypotheses (2021–2023 annual)

| hypothesis | model_2021 | model_2022 | model_2023 | rmse_mwh |
|---|---|---|---|---|
| all units | 26,682 | 24,801 | 25,323 | 7,123 |
| unit 4 out (mill units 1-3 only: 1,250 cfs, 3.05 MW) | 19,312 | 19,774 | 19,032 | 1,171 |
| mill out (unit 4 only: 800 cfs, 2.1 MW) | 14,094 | 14,276 | 13,467 | 4,750 |

**Reading:** the data favor "unit 4 out" over "mill units out" by a wide margin (RMSE ~1.2k vs
~4.7k MWh/yr). The effective limit (~2.5 MW / ~1,200 cfs) matches the mill units' hydraulic rating
(1,250 cfs). Their 3.05 MW nameplate is not reached at this head. eLibrary supports this: in July 2019
the operator filed **penstock wall repair** calculations (the concrete penstock feeds unit 4; EA §2.1.1),
followed by powerhouse intake repairs certified 2020-07 and closed 2021-05. Nothing found shows unit 4
returning to service. This is conditional on the v2 head/minimum-flow fit,
whose Q_minflow is at its bound. Treat it as supporting evidence, not confirmation. 2018 (ratio
0.73) may be the start of the regime, and 2019–2020 (ratios 0.38, 0.27) look like
deeper outages on top of it.

## "As-operated" hydrology scenarios (regime parameters on water years 1930-2023)

P90 **15,152** · P50 **19,187** · P10 **20,700** MWh/yr (mean 18,445).

## Per-year table 2001–2024 (v2 model)

| year | period | EIA MWh | modeled MWh (v2) | ratio | error % | mean flow cfs | flag |
|---|---|---|---|---|---|---|---|
| 2001 | other | 16,974 | 16,362 | 1.04 | -3.6 | 1,101 |  |
| 2002 | other | 4,439 | 18,417 | 0.24 | +314.9 | 1,232 | A4 actual < 50% of prior model at normal flow |
| 2003 | calibrate | 33,911 | 33,305 | 1.02 | -1.8 | 2,744 |  |
| 2004 | calibrate | 31,434 | 30,783 | 1.02 | -2.1 | 2,274 |  |
| 2005 | calibrate | 26,801 | 27,330 | 0.98 | +2.0 | 1,878 |  |
| 2006 | calibrate | 24,891 | 24,598 | 1.01 | -1.2 | 1,637 |  |
| 2007 | calibrate | 17,185 | 19,174 | 0.90 | +11.6 | 1,304 |  |
| 2008 | calibrate | 18,578 | 17,498 | 1.06 | -5.8 | 1,135 |  |
| 2009 | calibrate | 29,628 | 27,719 | 1.07 | -6.4 | 1,950 |  |
| 2010 | calibrate | 20,935 | 24,067 | 0.87 | +15.0 | 1,837 |  |
| 2011 | calibrate | 26,119 | 26,812 | 0.97 | +2.7 | 2,059 |  |
| 2012 | calibrate | 27,013 | 25,961 | 1.04 | -3.9 | 1,732 |  |
| 2013 | validate | 33,306 | 36,222 | 0.92 | +8.8 | 3,477 |  |
| 2014 | validate | 26,281 | 24,893 | 1.06 | -5.3 | 1,607 |  |
| 2015 | validate | 26,784 | 27,150 | 0.99 | +1.4 | 2,191 |  |
| 2016 | validate | 22,266 | 24,735 | 0.90 | +11.1 | 1,714 |  |
| 2017 | validate | 23,449 | 23,859 | 0.98 | +1.7 | 1,809 |  |
| 2018 | validate | 25,681 | 35,055 | 0.73 | +36.5 | 3,218 |  |
| 2019 | as_operated | 12,524 | 33,213 | 0.38 | +165.2 | 2,903 |  |
| 2020 | as_operated | 10,563 | 39,299 | 0.27 | +272.0 | 3,682 |  |
| 2021 | as_operated | 17,907 | 26,682 | 0.67 | +49.0 | 1,910 |  |
| 2022 | as_operated | 18,385 | 24,801 | 0.74 | +34.9 | 1,709 |  |
| 2023 | as_operated | 19,489 | 25,323 | 0.77 | +29.9 | 1,681 |  |
| 2024 | other | 17,870 | 28,528 | 0.63 | +59.6 | 2,423 | A1 known outage (Helene) |
