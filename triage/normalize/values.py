"""parsers for single raw values, each returns None when the value can't be trusted"""

from __future__ import annotations

import datetime as dt
import math
import re

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(value: object) -> dt.date | None:
    # a calendar date, datetimes are reduced to their utc calendar date
    moment = parse_datetime(value)
    return moment.date() if moment else None


def parse_datetime(value: object) -> dt.datetime | None:
    # an aware utc datetime, date-only strings become midnight utc, naive datetimes are read as utc
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        if _DATE_ONLY.match(text):
            day = dt.date.fromisoformat(text)
            return dt.datetime(day.year, day.month, day.day, tzinfo=dt.UTC)
        moment = dt.datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return moment.astimezone(dt.UTC)


def parse_number(value: object) -> float | None:
    # ints, floats and numeric strings, booleans and nan/inf are rejected
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def parse_bool(value: object) -> bool | None:
    # only real true/false count, "yes" or 1 are treated as unknown
    return value if isinstance(value, bool) else None


def parse_risk(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    risk = value.strip().upper()
    return risk if risk in ("LOW", "MODERATE", "HIGH") else None


def show(value: object) -> str:
    # a raw value as it appears in evidence, e.g. null, 'VERY_HIGH', 184
    if value is None:
        return "null"
    if isinstance(value, str):
        return repr(value)
    return str(value)
