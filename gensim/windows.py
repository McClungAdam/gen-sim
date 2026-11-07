"""Time-window masks shared by merge (fuel/DR/PPA windows) and dispatch (maintenance)."""
from __future__ import annotations

import pandas as pd

from gensim.timeutil import scalar_to_utc


def flag_windows(ts: pd.Series, windows, assume_tz: str) -> pd.Series:
    """1 where ts falls in any [start, end) window, else 0. Aligned to ts.index (defect #10:
    the legacy version indexed the mask by the timestamps themselves, so assigning it into the
    RangeIndex frame produced all-NaN flags).

    `ts` must be tz-aware UTC. Naive window bounds are human input in `assume_tz` (market time)."""
    mask = pd.Series(0, index=ts.index, dtype=int)
    for w in windows or []:
        try:
            if pd.isna(pd.to_datetime(w.get("start"))) or pd.isna(pd.to_datetime(w.get("end"))):
                continue
            s = scalar_to_utc(w.get("start"), assume_tz); e = scalar_to_utc(w.get("end"), assume_tz)
            mask |= ((ts >= s) & (ts < e)).astype(int)
        except Exception:
            continue
    return mask
