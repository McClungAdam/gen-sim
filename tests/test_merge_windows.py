"""Defect #10 (alignment) and #4 (window bounds are market-local time)."""
import pandas as pd

from gensim.windows import flag_windows

NY = "America/New_York"


def test_flags_align_with_rangeindex_frame():
    # 03:00-08:00 EST == 08:00-13:00 UTC
    df = pd.DataFrame({"timestamp": pd.date_range("2025-03-08 08:00", periods=6, freq="h", tz="UTC")})
    df["flag"] = flag_windows(df["timestamp"], [{"start": "2025-03-08 05:00", "end": "2025-03-08 07:00"}], NY)
    assert df["flag"].tolist() == [0, 0, 1, 1, 0, 0]


def test_no_windows_gives_zeros_not_nan():
    df = pd.DataFrame({"timestamp": pd.date_range("2025-03-08", periods=3, freq="h", tz="UTC")})
    df["flag"] = flag_windows(df["timestamp"], [], NY)
    assert df["flag"].tolist() == [0, 0, 0]


def test_overlapping_windows_union():
    ts = pd.Series(pd.date_range("2025-03-08 00:00", periods=5, freq="h", tz="UTC"))
    w = [{"start": "2025-03-08 00:00", "end": "2025-03-08 02:00"}, {"start": "2025-03-08 01:00", "end": "2025-03-08 03:00"}]
    assert flag_windows(ts, w, "UTC").tolist() == [1, 1, 1, 0, 0]


def test_offset_aware_bounds_are_respected():
    ts = pd.Series(pd.date_range("2025-03-08 00:00", periods=3, freq="h", tz="UTC"))
    w = [{"start": "2025-03-08T01:00:00+00:00", "end": "2025-03-08T02:00:00+00:00"}]
    assert flag_windows(ts, w, NY).tolist() == [0, 1, 0]
