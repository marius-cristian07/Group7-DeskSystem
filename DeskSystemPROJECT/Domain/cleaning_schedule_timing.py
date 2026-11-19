"""Convert daily local cleaning windows to timezone-aware UTC instants."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def next_occurrence(schedule, claimed_dates=(), now=None):
    # skip past starts and dates that already have a run
    if not schedule["is_enabled"]:
        return None
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo(schedule["timezone"])).date()
    for offset in range(370):
        day = today + timedelta(days=offset)
        if day in claimed_dates:
            continue
        try:
            start, end = get_window_utc(schedule, day)
        except ValueError:
            continue
        if start >= now and start >= schedule.get("created_at", now):
            return {"start_at": start, "end_at": end}
    return None


def get_window_utc(schedule, occurrence_date):
    zone = ZoneInfo(schedule["timezone"])
    start_time, end_time = schedule["start_time"], schedule["end_time"]

    end_date = occurrence_date
    if end_time < start_time:
        end_date += timedelta(days=1)

    start = datetime.combine(occurrence_date, start_time, tzinfo=zone)
    end = datetime.combine(end_date, end_time, tzinfo=zone)
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)

    for local, utc in ((start, start_utc), (end, end_utc)):
        # A spring DST change can skip a local time such as 02:30.
        if utc.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
            raise ValueError("Scheduled local time does not exist due to DST")
    if end_utc <= start_utc:
        raise ValueError("Cleaning end must be after start in UTC")
    return start_utc, end_utc
