# gen-sim

Small-scale generation economics. Phase 1: a **merchant asset screen** for existing PJM plants:
model output from resource data, value it against PJM energy + capacity revenue, and output the
maximum acquisition price. First test case: Fries Hydroelectric (FERC P-2883, EIA 10798).

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows; use .venv/bin/python elsewhere
.venv/Scripts/python -m pip install -e .                  # the gensim package
cp .env.example .env                                       # then fill in keys + contact email
```

Secrets live only in `.env` (gitignored). All data is fetched and cached locally; no CSVs are committed.

## Run

```bash
python run_pipeline.py --help            # fetch -> merge -> simulate; outputs in outputs/
streamlit run app/dashboard.py
python -m pytest                         # characterization goldens + unit tests
```

## Layout

```
gensim/        config.py (env, paths, config I/O), pipeline.py (single entry), merge.py
  data/        eia.py, market_prices.py (legacy, being removed), weather.py
  assets/      gas_genset.py
config/        gas_genset.json, operations_presets.json
app/           dashboard.py
tests/         fixtures/ (synthetic), golden/ (characterization), *.py
```

See `ASSUMPTIONS.md` for the running assumptions/decisions log.
