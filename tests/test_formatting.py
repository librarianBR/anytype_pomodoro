import datetime as dt

import pytest

from pomodoro_app.formatting import format_date, format_datetime, format_mmss, parse_date


@pytest.mark.parametrize("seconds, expected", [(0, "00:00"), (5, "00:05"), (125, "02:05"), (1500, "25:00"), (-3, "00:00")])
def test_format_mmss(seconds, expected):
    assert format_mmss(seconds) == expected


def test_format_dates():
    assert format_date(dt.date(2026, 11, 5)) == "05/11/2026"
    assert format_datetime(dt.datetime(2026, 11, 5, 9, 7)) == "05/11/2026 09:07"
    assert format_date(None) == "" and format_datetime(None) == ""


def test_parse_date():
    assert parse_date("15/11/2026") == dt.date(2026, 11, 15)
    assert parse_date("  ") is None


@pytest.mark.parametrize("text", ["2026-11-15", "31/02/2026", "15/11"])
def test_parse_date_invalid(text):
    with pytest.raises(ValueError):
        parse_date(text)
