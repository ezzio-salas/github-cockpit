from datetime import datetime, timedelta, timezone

import pytest

from cockpit_core.relative_time import age, compact

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0, "0s"),
        (59, "59s"),
        (60, "1m"),
        (119, "1m"),
        (3599, "59m"),
        (3600, "1h"),
        (86_399, "23h"),
        (86_400, "1d"),
        (200_000, "2d"),
    ],
)
def test_compact_uses_the_longest_unit_that_is_at_least_one(seconds, expected):
    assert compact(seconds) == expected


def test_compact_never_shows_a_negative_duration():
    assert compact(-5) == "0s"


@pytest.mark.parametrize(
    "delta, expected",
    [
        (timedelta(seconds=0), "JUST NOW"),
        (timedelta(seconds=59), "JUST NOW"),
        (timedelta(minutes=5), "5M AGO"),
        (timedelta(hours=3), "3H AGO"),
        (timedelta(days=2), "2D AGO"),
    ],
)
def test_age_reads_as_time_since_the_pull_request_changed(delta, expected):
    assert age(NOW - delta, NOW) == expected


def test_a_pull_request_with_no_timestamp_shows_no_age():
    assert age(None, NOW) == ""


def test_a_clock_slightly_ahead_reads_as_just_now_rather_than_a_negative_age():
    assert age(NOW + timedelta(minutes=2), NOW) == "JUST NOW"
