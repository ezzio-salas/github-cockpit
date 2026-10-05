"""Short durations, for the stale marker and the age of a pull request."""

from __future__ import annotations

from datetime import datetime

_MINUTE = 60
_HOUR = 60 * _MINUTE
_DAY = 24 * _HOUR


def compact(seconds: float) -> str:
    """`30s`, `5m`, `3h`, `2d` — the longest unit that is at least 1, for the header marker."""
    seconds = max(seconds, 0)
    if seconds < _MINUTE:
        return f"{int(seconds)}s"
    if seconds < _HOUR:
        return f"{int(seconds // _MINUTE)}m"
    if seconds < _DAY:
        return f"{int(seconds // _HOUR)}h"
    return f"{int(seconds // _DAY)}d"


def age(moment: datetime | None, now: datetime) -> str:
    """`JUST NOW`, `5M AGO`, `2D AGO`; empty when there is no timestamp.

    A moment in the future reads as `JUST NOW` rather than a negative age, because a clock
    a little out of step should not look like a bug.
    """
    if moment is None:
        return ""
    seconds = (now - moment).total_seconds()
    if seconds < _MINUTE:
        return "JUST NOW"
    return f"{compact(seconds).upper()} AGO"
