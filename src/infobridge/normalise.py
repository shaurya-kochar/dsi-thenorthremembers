"""Value normalisation shared by the extractor and the conflict detector.

Values are normalised so that the same fact written two ways compares equal:
dates -> YYYY-MM-DD, phones -> last 10 digits, times -> HH:MM (24h),
counts -> plain integers. The original text is always kept as ``raw_value``.
"""

from __future__ import annotations

import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}

ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
NUMERIC = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")  # dd/mm/yyyy (Indian order)
DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?(?:\s+(\d{4}))?")
MONTH_DAY = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?(?:\s+(\d{4}))?")
TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([AaPp]\.?[Mm]\.?)?\b")


def _month(word: str) -> int | None:
    return MONTHS.get(word[:3].lower()) if len(word) >= 3 else None


def _date(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def normalise_date(raw: str, default_year: int | None = None) -> str | None:
    """First date in ``raw`` as YYYY-MM-DD, or None. Numeric dates are read day-first."""
    text = raw.strip()
    if m := ISO.search(text):
        return _date(int(m[1]), int(m[2]), int(m[3]))
    if m := NUMERIC.search(text):
        year = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        return _date(year, int(m[2]), int(m[1]))
    for pattern, day_group, month_group in ((DAY_MONTH, 1, 2), (MONTH_DAY, 2, 1)):
        for m in pattern.finditer(text):
            month = _month(m[month_group])
            year = int(m[3]) if m[3] else default_year
            if month and year:
                return _date(year, month, int(m[day_group]))
    return None


def normalise_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    return digits[-10:] if len(digits) >= 10 else None


def normalise_time(raw: str) -> str | None:
    """'5:30 AM' / '05:30' / '6:30 pm' / '11 pm' -> 'HH:MM' (24h)."""
    for m in TIME.finditer(raw):
        hour, minute, ampm = int(m[1]), int(m[2] or 0), (m[3] or "").lower().replace(".", "")
        if not m[2] and not ampm:
            continue  # a bare number is not a time
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        if hour < 24 and minute < 60:
            return f"{hour:02d}:{minute:02d}"
    return None


def normalise_count(raw: str) -> str | None:
    if m := re.search(r"\d+(?:\.\d+)?", raw):
        number = float(m[0])
        return str(int(number)) if number.is_integer() else str(number)
    for word in re.findall(r"[a-z]+", raw.lower()):
        if word in NUMBER_WORDS:
            return str(NUMBER_WORDS[word])
    return None


DATE_ATTRIBUTES = {"membership_valid_until", "joined_on", "medical_clearance_date", "registered_on",
                   "batch_start_date", "registration_deadline", "event_date"}
TIME_ATTRIBUTES = {"start_time", "briefing_time", "check_in_time", "end_time", "opening_time"}
COUNT_ATTRIBUTES = {"distance_km", "volunteer_count", "volunteers_present", "water_crates"}


def normalise_value(attribute: str, raw: str, default_year: int | None = None) -> str:
    """Normalised form of ``raw`` for ``attribute``; falls back to the trimmed text."""
    raw = str(raw).strip()
    if attribute in DATE_ATTRIBUTES:
        value = normalise_date(raw, default_year)
    elif attribute in TIME_ATTRIBUTES:
        value = normalise_time(raw)
    elif attribute == "phone":
        value = normalise_phone(raw)
    elif attribute == "email":
        value = raw.lower()
    elif attribute in COUNT_ATTRIBUTES:
        value = normalise_count(raw)
    else:
        value = re.sub(r"\s+", " ", raw)
    return value or raw
