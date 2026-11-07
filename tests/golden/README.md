# Golden outputs (characterization)

Provenance: generated 2026-11-06 by `tests/test_characterization.py` with `GENSIM_UPDATE_GOLDEN=1`,
running the **unmodified** Original_GenSim code (commit d003157) under pandas 2.3.3 / numpy 2.5.4 /
Python 3.14, on the synthetic fixture in `tests/fixtures/` (no real API data), clock frozen at
2025-03-12 00:00.

They pin behavior **including known bugs**. Notable bugs visible in these files:

| File | What the golden shows | Defect |
|---|---|---|
| `purpa/merged_inputs.csv` | `fuel_available`, `event_active`, `ppa_active` blank on every row | #10 (window flags misaligned) |
| `purpa/simulation_results.csv` | gen_1 never runs (0 of 114 h) despite a PPA window | #10 |
| `wholesale/simulation_results.csv` | gen_1 runs 6 h inside its 2025-03-10 08:00–16:00 maintenance window | #8 |
| `*/merged_inputs.csv` | `gas_price` blank after the last daily print (2025-03-11 01:00–19:00) | #5 (Original variant) |
| `normalized_prices_normal.csv` | the 2025-03-09T02 row is shifted to 03:00 and the real 03:00 row dropped (DST) | #4 |
| ~~`normalized_prices_large.csv`~~ | removed in the #1 fix: demand-sized input now raises (`tests/test_market_prices.py`) | #1 fixed |

Rules: a refactor must reproduce these exactly (rtol 1e-9). A defect fix that changes them updates
the affected files in the same commit and explains the change in the commit message.

## Change log

- **#1/#2 fix:** deleted `normalized_prices_large.csv` (the ÷100 path is gone; the input now raises). No other golden changed.
