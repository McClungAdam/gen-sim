"""Time-window masks shared by merge (fuel/DR/PPA windows) and dispatch (maintenance)."""
from __future__ import annotations

import pandas as pd


def flag_windows(ts: pd.Series, windows) -> pd.Series:
    """1 where ts falls in any [start, end) window, else 0. Aligned to ts.index (defect #10:
    the legacy version indexed the mask by the timestamps themselves, so assigning it into the
    RangeIndex frame produced all-NaN flags)."""
    mask = pd.Series(0, index=ts.index, dtype=int)
    for w in windows or []:
        try:
            s = pd.to_datetime(w.get("start")); e = pd.to_datetime(w.get("end"))
            if pd.isna(s) or pd.isna(e):
                continue
            mask |= ((ts >= s) & (ts < e)).astype(int)
        except Exception:
            continue
    return mask
