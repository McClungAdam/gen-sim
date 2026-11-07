# Golden outputs (characterization)

Provenance: generated 2026-11-06 by `tests/test_characterization.py` with `GENSIM_UPDATE_GOLDEN=1`,
running the **unmodified** Original_GenSim code (commit d003157) under pandas 2.3.3 / numpy 2.5.4 /
Python 3.14, on the synthetic fixture in `tests/fixtures/` (no real API data), clock frozen at
2025-03-12 00:00.

They pin behavior **including known bugs**. Notable bugs visible in these files:

| File | What the golden shows | Defect |
|---|---|---|
| `purpa/merged_inputs.csv` | ~~flags blank on every row~~ | #10 fixed |
| `purpa/simulation_results.csv` | ~~gen_1 never runs~~ → runs 70 h, only inside the PPA window, never during curtailment | #10 fixed |
| `wholesale/simulation_results.csv` | ~~gen_1 runs 6 h inside its maintenance window~~ → 0 h | #8 fixed |
| `*/merged_inputs.csv` | `gas_price` blank after the last daily print (2025-03-11 01:00–19:00) | #5 (Original variant) |
| `normalized_prices_normal.csv` | the 2025-03-09T02 row is shifted to 03:00 and the real 03:00 row dropped (DST) | #4 |
| ~~`normalized_prices_large.csv`~~ | removed in the #1 fix: demand-sized input now raises (`tests/test_market_prices.py`) | #1 fixed |

Rules: a refactor must reproduce these exactly (rtol 1e-9). A defect fix that changes them updates
the affected files in the same commit and explains the change in the commit message.

## Change log

- **#1/#2 fix:** deleted `normalized_prices_large.csv` (the ÷100 path is gone; the input now raises). No other golden changed.
- **#10 fix:** window flags populated. Changed columns: `event_active` (NaN→0) in wholesale merged/sim; `fuel_available`, `event_active`, `ppa_active` and gen_1 output/profit/run in purpa. Weather goldens unchanged.
- **#8 fix:** maintenance windows applied. Only `wholesale/simulation_results.csv` changed: gen_1 output/profit/run in the 6 in-window hours (52→46 run h, profit $1,457.56→$1,308.50). No other rows or files changed.
