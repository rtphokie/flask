import csv
import os
import uuid
from datetime import datetime, timezone

from flask import Flask, Response, jsonify

app = Flask(__name__)


@app.route('/')
def index():
    return jsonify({"attr": "value"})


def _parse_iso_datetime(s: str):
    """
    Parse an ISO-like datetime string into a timezone-aware datetime in UTC if possible.
    Accepts forms like:
      - 2025-12-31T23:00:00Z
      - 2025-12-31T15:00:00+03:00
      - 2025-12-31T23:00:00  (treated as UTC)
    """
    if not s:
        return None
    s = s.strip()
    # Normalize trailing Z
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        # Fallback: try common format without fractional seconds
        try:
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    # If aware -> convert to UTC; if naive -> assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_ics_dt(dt: datetime):
    """
    Format datetime for ICS: use UTC 'YYYYMMDDTHHMMSSZ'
    """
    return dt.strftime('%Y%m%dT%H%M%SZ')


def _load_events_from_csv(csv_path):
    events = []
    with open(csv_path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Expected CSV headers (case-insensitive): uid, title, description, dtstart, dtend, url, location
            uid = (row.get('uid') or row.get('id') or '').strip() or str(uuid.uuid4())
            title = (row.get('title') or row.get('summary') or '').strip()
            description = (row.get('description') or '').strip()
            dtstart_raw = (row.get('dtstart') or row.get('start') or '').strip()
            dtend_raw = (row.get('dtend') or row.get('end') or '').strip()
            url = (row.get('url') or '').strip()
            location = (row.get('location') or '').strip()

            dtstart = _parse_iso_datetime(dtstart_raw)
            dtend = _parse_iso_datetime(dtend_raw)

            # Skip rows without a start
            if not dtstart:
                continue

            events.append({
                'uid': uid,
                'title': title,
                'description': description,
                'dtstart': dtstart,
                'dtend': dtend,
                'url': url,
                'location': location,
            })
    return events


@app.route('/calendar.ics')
def calendar():
    # CSV path relative to this file
    base_dir = os.path.dirname(__file__)
    csv_path = os.path.join(base_dir, 'data', 'events.csv')

    events = _load_events_from_csv(csv_path)
    now = datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//WhatsUpInSpace//Railway Flask ICS//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        # Add calendar title/description and refresh hints (every minute)
        "X-WR-CALNAME:Whats Up 1.2",
        "X-WR-CALDESC:Whats Up 1.21",
        "X-PUBLISHED-TTL:PT1M",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1M",
    ]

    for ev in events:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{ev['uid']}")
        lines.append(f"DTSTAMP:{_format_ics_dt(now)}")
        lines.append(f"DTSTART:{_format_ics_dt(ev['dtstart'])}")
        if ev['dtend']:
            lines.append(f"DTEND:{_format_ics_dt(ev['dtend'])}")
        # Escape newlines in description per RFC
        desc = ev['description'].replace('\r\n', '\\n').replace('\n', '\\n')
        if ev['title']:
            lines.append(f"SUMMARY:{ev['title']}")
            print(f"Adding event: {ev['title']}")
        if desc:
            lines.append(f"DESCRIPTION:{desc}")
        if ev['location']:
            lines.append(f"LOCATION:{ev['location']}")
        if ev['url']:
            lines.append(f"URL:{ev['url']}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    ics_body = "\r\n".join(lines) + "\r\n"
    headers = {
        "Content-Type": "text/calendar; charset=utf-8",
        "Content-Disposition": 'inline; filename="whatsup.ics"',
        # Allow caching by calendar clients, but you may customize
    }
    return Response(ics_body, headers=headers)


if __name__ == '__main__':
    app.run(debug=True, port=os.getenv("PORT", default=5000))
