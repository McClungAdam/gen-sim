import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parent, HERE):  # repo root (legacy flat modules) and tests/ (helpers)
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
