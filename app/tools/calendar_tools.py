"""Reads the day's events from your real calendar: a private iCal link (live) or an uploaded .ics file.

Google Calendar and Outlook both give each calendar a secret iCal address, so the app
can read your schedule without any sign-in or extra API key. Repeating events (weekly
classes) are expanded, and times are converted to your time zone.
"""

from __future__ import annotations

import ssl
import time as _time
import urllib.request
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import certifi
import recurring_ical_events
from icalendar import Calendar

from ..safety import clean_untrusted

_SSL = ssl.create_default_context(cafile=certifi.where())
_CACHE: dict[str, tuple[float, bytes]] = {}
CACHE_SECONDS = 600
MAX_ICS_BYTES = 5 * 1024 * 1024


class CalendarLinkError(RuntimeError):
    pass


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if not url.startswith("https://"):
        raise CalendarLinkError("The calendar link should start with https:// (or webcal://).")
    return url


def fetch_ics(url: str) -> bytes:
    """Download a private iCal feed (cached for 10 minutes). The URL itself is never logged."""
    url = normalize_url(url)
    hit = _CACHE.get(url)
    if hit and _time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ClosetTwin/1.0"})
        with urllib.request.urlopen(req, timeout=12, context=_SSL) as r:
            raw = r.read(MAX_ICS_BYTES + 1)
    except Exception as e:
        raise CalendarLinkError(f"Couldn't read the calendar link ({type(e).__name__}).") from None
    if len(raw) > MAX_ICS_BYTES or b"BEGIN:VCALENDAR" not in raw[:4000]:
        raise CalendarLinkError("That link didn't return an iCal calendar. Use the 'secret address in iCal format'.")
    _CACHE[url] = (_time.time(), raw)
    return raw


def _local(dt, tz):
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            dt = dt.astimezone(tz) if tz else dt.astimezone()
        return dt.date(), dt.time()
    return dt, None  # all-day event (a date)


def _event_dict(ev, s_time, e_time) -> dict:
    # Event titles and notes can come from other people's invites: treat as untrusted text.
    title, _ = clean_untrusted(str(ev.get("SUMMARY", "")), 120)
    location, _ = clean_untrusted(str(ev.get("LOCATION", "")), 120)
    notes, _ = clean_untrusted(str(ev.get("DESCRIPTION", "")), 200)
    return {"start": s_time.strftime("%H:%M"), "end": e_time.strftime("%H:%M"),
            "title": title, "location": location, "notes": notes}


def events_from_ics(raw: bytes, day: str, remap_to_day: bool = False, tz_name: str | None = None) -> list[dict]:
    """Events on `day`, earliest first. With remap_to_day (sample data) every event is moved onto `day`."""
    cal = Calendar.from_ical(raw)
    tz = ZoneInfo(tz_name) if tz_name else None
    out = []
    if remap_to_day:
        for ev in cal.walk("VEVENT"):
            _, s = _local(ev.decoded("DTSTART"), tz)
            _, e = _local(ev.decoded("DTEND"), tz) if ev.get("DTEND") else (None, s)
            out.append(_event_dict(ev, s or time(0, 0), e or time(23, 59)))
        return sorted(out, key=lambda x: x["start"])
    target = date.fromisoformat(day)
    for ev in recurring_ical_events.of(cal).at(target):
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        s_day, s = _local(ev.decoded("DTSTART"), tz)
        _, e = _local(ev.decoded("DTEND"), tz) if ev.get("DTEND") else (None, s)
        if s is None:  # all-day
            out.append(_event_dict(ev, time(0, 0), time(23, 59)) | {"all_day": True})
        elif s_day == target:
            out.append(_event_dict(ev, s, e or s))
    return sorted(out, key=lambda x: x["start"])


def events_for(path, day: str, remap_to_day: bool = False, tz_name: str | None = None) -> list[dict]:
    """Events from an .ics file on disk (kept for the uploaded-file path and tests)."""
    if not path.exists():
        return []
    return events_from_ics(path.read_bytes(), day, remap_to_day, tz_name)
