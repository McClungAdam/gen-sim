"""Defect #4: one timestamp convention (tz-aware UTC), explicit assumptions for naive input."""
import pandas as pd
import pytest

from gensim.data.market_prices import normalize_prices_df
from gensim.timeutil import NaiveTimestampError, dates_to_utc_day_start, scalar_to_utc, series_to_utc

NY = "America/New_York"


def test_offsets_converted_to_utc():
    s = series_to_utc(["2025-07-01T12:00:00-04:00", "2025-01-01T12:00:00-05:00"], None)
    assert [str(x) for x in s] == ["2025-07-01 16:00:00+00:00", "2025-01-01 17:00:00+00:00"]


def test_naive_without_assumption_raises():
    with pytest.raises(NaiveTimestampError, match="refusing to guess"):
        series_to_utc(["2025-07-01 12:00:00"], None)


def test_mixed_naive_and_aware_raises():
    with pytest.raises(NaiveTimestampError, match="Mixed"):
        series_to_utc(["2025-07-01 12:00:00", "2025-07-01T13:00:00+00:00"], NY)


def test_naive_market_time_both_dst_seasons():
    s = series_to_utc(["2025-01-15 12:00", "2025-07-15 12:00"], NY)
    assert [x.hour for x in s] == [17, 16]


def test_spring_forward_gap_raises_instead_of_shifting():
    # Legacy: 02:00 on 2025-03-09 was shifted to 03:00 and the real 03:00 row dropped.
    with pytest.raises(NaiveTimestampError):
        series_to_utc(["2025-03-09 01:00", "2025-03-09 02:00", "2025-03-09 03:00"], NY)


def test_fall_back_repeated_hour_inferred_from_order():
    s = series_to_utc(["2025-11-02 00:00", "2025-11-02 01:00", "2025-11-02 01:00", "2025-11-02 02:00"], NY)
    assert [str(x) for x in s] == [
        "2025-11-02 04:00:00+00:00", "2025-11-02 05:00:00+00:00",
        "2025-11-02 06:00:00+00:00", "2025-11-02 07:00:00+00:00",
    ]


def test_gas_day_starts_at_local_midnight():
    s = dates_to_utc_day_start(["2025-03-07", "2025-03-10"], NY)  # EST, then EDT
    assert [str(x) for x in s] == ["2025-03-07 05:00:00+00:00", "2025-03-10 04:00:00+00:00"]


def test_scalar_window_bound():
    assert str(scalar_to_utc("2025-07-04 14:00", NY)) == "2025-07-04 18:00:00+00:00"


def test_eia_style_utc_prices_keep_every_hour_across_dst():
    raw = pd.DataFrame({"period": [f"2025-03-09T{h:02d}" for h in range(0, 6)], "value": range(30, 36)})
    out = normalize_prices_df(raw, assume_tz="UTC")
    assert len(out) == 6
    assert out["timestamp"].dt.tz is not None
    assert out["timestamp"].diff().dropna().eq(pd.Timedelta(hours=1)).all()
