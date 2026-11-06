# gen-sim

Small-scale generation economics. Phase 1: a **merchant asset screen** for existing PJM plants:
model output from resource data, value it against PJM energy + capacity revenue, and output the
maximum acquisition price. First test case: Fries Hydroelectric (FERC P-2883, EIA 10798).

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows; use .venv/bin/python elsewhere
cp .env.example .env                                       # then fill in keys + contact email
```

Secrets live only in `.env` (gitignored). All data is fetched and cached locally; no CSVs are committed.

See `ASSUMPTIONS.md` for the running assumptions/decisions log.
