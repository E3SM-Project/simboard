from datetime import date, datetime, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from app.common.model_dates import ModelDate, add_model_date, normalize_model_date


@pytest.mark.parametrize(
    "value, expected",
    [
        ("0000-01-01", "0000-01-01"),
        ("0000-01-02", "0000-01-02"),
        ("0000-02-29", "0000-02-29"),
        ("0001-01-01", "0001-01-01"),
        ("9999-12-31", "9999-12-31"),
        (date(2020, 1, 2), "2020-01-02"),
        (datetime(2020, 1, 2, tzinfo=timezone.utc), "2020-01-02"),
        ("2020-01-02T00:00:00Z", "2020-01-02"),
        ("2020-01-01T19:00:00-05:00", "2020-01-02"),
    ],
)
def test_model_dates_normalize_without_changing_year(value, expected):
    adapter = TypeAdapter(ModelDate)
    result = adapter.validate_python(value)
    assert result == expected
    assert adapter.dump_json(result) == f'"{expected}"'.encode()


@pytest.mark.parametrize(
    "value",
    [
        None,
        0,
        "",
        "not-a-date",
        "0000-13-01",
        "0000-00-01",
        "0000-01-00",
        "0000-02-30",
        "0001-02-29",
        "1900-02-29",
        "2020-1-2",
        "10000-01-01",
        "-0001-01-01",
        "2020-01-01T01:00:00Z",
        "0001-01-01T00:00:00+01:00",
        "9999-12-31T23:00:00-02:00",
    ],
)
def test_invalid_model_dates_are_rejected(value):
    with pytest.raises(ValidationError):
        TypeAdapter(ModelDate).validate_python(value)


@pytest.mark.parametrize(
    "value, days, months, expected",
    [
        ("0000-01-01", 0, 0, "0000-01-01"),
        ("0000-01-02", 1, 0, "0000-01-03"),
        ("0000-02-28", 1, 0, "0000-02-29"),
        ("0000-12-31", 1, 0, "0001-01-01"),
        ("0001-01-01", -1, 0, "0000-12-31"),
        ("0000-01-01", 366, 0, "0001-01-01"),
        ("0000-01-31", 0, 1, "0000-02-29"),
        ("0000-02-29", 0, 12, "0001-02-28"),
        ("2020-01-31", 0, 1, "2020-02-29"),
        ("0000-01-01", 3652424, 0, "9999-12-31"),
    ],
)
def test_model_date_arithmetic(value, days, months, expected):
    assert add_model_date(value, days=days, months=months) == expected


@pytest.mark.parametrize(
    "value, days, months",
    [("0000-01-01", -1, 0), ("0000-01-01", 0, -1), ("9999-12-31", 1, 0)],
)
def test_model_date_arithmetic_rejects_out_of_range(value, days, months):
    with pytest.raises(ValueError, match="between 0000 and 9999"):
        add_model_date(value, days=days, months=months)


def test_fixed_width_dates_sort_chronologically():
    dates = ["0001-01-01", "0000-12-31", "2020-01-01", "0000-01-02"]
    assert sorted(dates) == ["0000-01-02", "0000-12-31", "0001-01-01", "2020-01-01"]
    assert normalize_model_date("0000-01-02") == "0000-01-02"
