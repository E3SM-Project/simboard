"""Gregorian model dates, including astronomical year zero.

Model dates are stored as fixed-width strings, not Python calendar objects.
Real execution timestamps must continue to use timezone-aware datetimes.
"""

import calendar
import re
from datetime import date, datetime, time, timezone
from typing import Annotated

from pydantic import BeforeValidator, Field


def normalize_model_date(value: object) -> str:
    """Validate a model date and normalize legacy midnight datetime inputs."""
    if isinstance(value, str):
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            year, month, day = map(int, value.split("-"))

            if (
                not 1 <= month <= 12
                or not 1 <= day <= calendar.monthrange(year, month)[1]
            ):
                raise ValueError("Invalid model date")

            return value

        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Model date must use YYYY-MM-DD") from exc

    if isinstance(value, datetime):
        try:
            value = value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(
                timezone.utc
            )
        except OverflowError as exc:
            raise ValueError("Model datetime is outside the supported range") from exc

        if value.time() != time.min:
            raise ValueError("Model date datetime must represent midnight UTC")

        value = value.date()

    if isinstance(value, date):
        return value.isoformat()

    raise ValueError("Model date must use YYYY-MM-DD")


ModelDate = Annotated[
    str,
    BeforeValidator(normalize_model_date),
    Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
]


def add_model_date(value: str, *, days: int = 0, months: int = 0) -> str:
    """Add months (clamping month ends), then days, including year zero."""
    year, month, day = map(int, normalize_model_date(value).split("-"))
    year, month_index = divmod(year * 12 + month - 1 + months, 12)
    month = month_index + 1

    if not 0 <= year <= 9999:
        raise ValueError("Model date year must be between 0000 and 9999")

    day = min(day, calendar.monthrange(year, month)[1])

    # Year zero is a leap year. Ordinal 1 remains 0001-01-01.
    ordinal = (
        date(year, month, day).toordinal()
        if year
        else date(400, month, day).toordinal() - date(401, 1, 1).toordinal() + 1
    )
    ordinal += days

    if not -365 <= ordinal <= date.max.toordinal():
        raise ValueError("Model date year must be between 0000 and 9999")

    if ordinal <= 0:
        shifted = date.fromordinal(date(401, 1, 1).toordinal() + ordinal - 1)

        return f"0000-{shifted.month:02d}-{shifted.day:02d}"

    return date.fromordinal(ordinal).isoformat()
