"""Timestamp convention (defect #4): tz-aware UTC everywhere inside the pipeline.

Only two places interpret naive (zone-less) times, and both say which zone they assume:
  * human inputs (config windows, --as-of, user price files): the market's local zone;
  * external sources whose zone is documented (EIA-930 periods are UTC).
Files the pipeline writes always carry an explicit offset (+00:00). Display code converts to the
market zone at the last moment.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

DEFAULT_MARKET_TZ = "America/New_York"   # PJM (EPT) and Duke are both US/Eastern


def market_tz(cfg: dict | None) -> str:
    return ((cfg or {}).get("market") or {}).get("timezone", DEFAULT_MARKET_TZ)


class NaiveTimestampError(ValueError):
    """A file that must carry explicit offsets contains zone-less timestamps."""


def series_to_utc(values, assume_tz: str | None) -> pd.Series:
    """Parse to tz-aware UTC.

    Values with offsets are converted. Naive values are localized to `assume_tz`
    (DST: repeated fall-back hours are inferred from order; spring-forward gaps raise),
    or raise NaiveTimestampError if assume_tz is None.
    """
    s = pd.Series(values)
    if s.empty:
        return pd.to_datetime(s, utc=True)
    as_str = s.astype(str)
    has_offset = as_str.str.contains(r"(?:[+-]\d{2}:?\d{2}|Z|UTC)$", regex=True)
    if has_offset.all():
        return pd.to_datetime(s, utc=True)
    if has_offset.any():
        raise NaiveTimestampError("Mixed naive and offset-aware timestamps in one column.")
    if assume_tz is None:
        raise NaiveTimestampError(
            f"Timestamps have no UTC offset (e.g. {as_str.iloc[0]!r}); refusing to guess the zone."
        )
    naive = pd.to_datetime(s)
    try:
        local = naive.dt.tz_localize(assume_tz, ambiguous="infer", nonexistent="raise")
    except Exception as e:  # pytz/zoneinfo raise different types for DST problems
        raise NaiveTimestampError(f"Cannot place naive times in {assume_tz}: {e}") from e
    return local.dt.tz_convert("UTC")


def scalar_to_utc(value, assume_tz: str) -> pd.Timestamp:
    """One human-entered time (window bound, --as-of). Naive -> assume_tz."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(assume_tz, nonexistent="raise", ambiguous="raise")
    return ts.tz_convert("UTC")


def now_utc(now: datetime | None, assume_tz: str) -> pd.Timestamp:
    return scalar_to_utc(now, assume_tz) if now is not None else pd.Timestamp.now(tz="UTC")


def dates_to_utc_day_start(values, tz: str) -> pd.Series:
    """Calendar dates (e.g. daily gas prints) -> the start of that day in `tz`, as UTC."""
    d = pd.to_datetime(pd.Series(values)).dt.normalize()
    if isinstance(d.dtype, pd.DatetimeTZDtype):
        d = d.dt.tz_localize(None)
    return d.dt.tz_localize(tz).dt.tz_convert("UTC")
