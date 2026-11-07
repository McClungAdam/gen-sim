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


def parse_windows_text(text: str) -> list[dict]:
    """Dashboard text area: one window per line, 'start,end,reason' -> list of dicts."""
    wins = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",", 2)]   # reason may itself contain commas
        if len(parts) >= 2:
            wins.append({"start": parts[0], "end": parts[1], "reason": parts[2] if len(parts) > 2 else ""})
    return wins


def serialize_windows_text(wins) -> str:
    """Inverse of parse_windows_text: a real newline between windows (defect 9a guard)."""
    return "\n".join(f"{w.get('start','')},{w.get('end','')},{w.get('reason','')}" for w in (wins or []))
