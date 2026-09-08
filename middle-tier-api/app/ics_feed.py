"""iCalendar (.ics) generation.

Hand-rolled rather than pulled from a library: the format is small, and a
subscribable feed with no extra dependency is easier to demo and to grade.
Google Calendar, Apple Calendar, and Outlook all subscribe to a plain URL.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

PRODID = "-//SyllaSync//Syllabus Deadlines//EN"


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 caps content lines at 75 octets."""
    if len(line) <= 75:
        return line
    out, rest = [line[:75]], line[75:]
    while rest:
        out.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(out)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    if "T" not in text:
        # A date with no time means end of that day, not midnight at its start.
        text += "T23:59:59+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_feed(tasks: List[Dict[str, Any]], calendar_name: str = "SyllaSync") -> str:
    now = datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        "X-PUBLISHED-TTL:PT1H",
    ]

    for task in tasks:
        window = task.get("window") or {}
        start = _parse(window.get("start")) or _parse(task.get("dueAt"))
        if start is None:
            continue  # a deadline with no date isn't a calendar event
        end = _parse(window.get("end")) or (start + timedelta(minutes=30))

        course = task.get("courseCode") or task.get("courseTitle") or ""
        title = task.get("title") or "Untitled"
        summary = f"{course}: {title}" if course else title

        description_parts = [p for p in (task.get("description"), task.get("sourceText")) if p]
        if task.get("weightPct") is not None:
            description_parts.append(f"Worth {task['weightPct']}% of the final grade.")

        event = [
            "BEGIN:VEVENT",
            f"UID:{task.get('id', 'unknown')}@syllasync.local",
            f"DTSTAMP:{_stamp(now)}",
            f"DTSTART:{_stamp(start)}",
            f"DTEND:{_stamp(end)}",
            f"SUMMARY:{_escape(summary)}",
            f"CATEGORIES:{_escape(task.get('type') or 'OTHER')}",
            "BEGIN:VALARM",
            "TRIGGER:-P1D",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_escape(summary)} is due tomorrow",
            "END:VALARM",
        ]
        if description_parts:
            event.insert(6, f"DESCRIPTION:{_escape(' | '.join(description_parts))}")
        event.append("END:VEVENT")
        lines.extend(event)

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
