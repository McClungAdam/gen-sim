"""Defect #10: window flags must align with the merged frame (legacy produced all-NaN flags)."""
import pandas as pd

from gensim.merge import _flag_windows


def test_flags_align_with_rangeindex_frame():
    df = pd.DataFrame({"timestamp": pd.date_range("2025-03-08 03:00", periods=6, freq="h")})
    df["flag"] = _flag_windows(df["timestamp"], [{"start": "2025-03-08 05:00", "end": "2025-03-08 07:00"}])
    assert df["flag"].tolist() == [0, 0, 1, 1, 0, 0]


def test_no_windows_gives_zeros_not_nan():
    df = pd.DataFrame({"timestamp": pd.date_range("2025-03-08", periods=3, freq="h")})
    df["flag"] = _flag_windows(df["timestamp"], [])
    assert df["flag"].tolist() == [0, 0, 0]


def test_overlapping_windows_union():
    ts = pd.Series(pd.date_range("2025-03-08 00:00", periods=5, freq="h"))
    w = [{"start": "2025-03-08 00:00", "end": "2025-03-08 02:00"}, {"start": "2025-03-08 01:00", "end": "2025-03-08 03:00"}]
    assert _flag_windows(ts, w).tolist() == [1, 1, 1, 0, 0]
