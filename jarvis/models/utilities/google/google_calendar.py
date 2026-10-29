from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from urllib.parse import quote

from google_auth import GoogleError, api
from google_common import approve, declined, safe

BASE = "https://www.googleapis.com/calendar/v3"


def _path(calendar_id):
    # Calendar ids contain characters like '#' and '@' that have to be escaped in a URL path
    return quote(calendar_id, safe="")


def _local(text):
    """Parses a time like '2026-10-30 15:00' as local time (or keeps a zone if it has one)."""
    try:
        parsed = datetime.fromisoformat(str(text).strip().replace(" ", "T"))
    except ValueError:
        raise GoogleError(f"Couldn't read the time '{text}'. Use a form like 2026-10-30 15:00.")
    return parsed.astimezone()  # a naive time is taken to be local


def _show(moment):
    """An event time from Google ('dateTime' or all-day 'date') as a readable local time."""
    if "dateTime" in moment:
        return datetime.fromisoformat(moment["dateTime"].replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    return moment.get("date")


def _event(raw, calendar=None):
    result = {
        "id": raw["id"],
        "title": raw.get("summary", "(no title)"),
        "start": _show(raw.get("start", {})),
        "end": _show(raw.get("end", {})),
        "all_day": "date" in raw.get("start", {}),
    }
    if calendar:
        result["calendar"] = calendar["name"]
        result["calendar_id"] = calendar["id"]
    for source, name in (("location", "location"), ("description", "description"), ("htmlLink", "link")):
        if raw.get(source):
            result[name] = raw[source]
    people = [a["email"] for a in raw.get("attendees", []) if not a.get("self")]
    if people:
        result["attendees"] = people
    return result


def _starts_at(raw):
    """When an event starts, as a comparable time, so events from different calendars can be put in order."""
    moment = raw.get("start", {})
    if "dateTime" in moment:
        return datetime.fromisoformat(moment["dateTime"].replace("Z", "+00:00")).astimezone()
    return datetime.combine(datetime.fromisoformat(moment["date"]).date(), time.min).astimezone()


# ---------------------------------------------------------------------------------------------- calendars

def _calendars():
    """Every calendar the user has: their own, shared ones, and subscribed ones such as a school or holiday calendar."""
    listing = api("GET", f"{BASE}/users/me/calendarList", params={"minAccessRole": "reader", "maxResults": 250}).get("items", [])
    return [
        {"id": item["id"], "name": item.get("summaryOverride") or item.get("summary") or item["id"], "primary": bool(item.get("primary")), "role": item.get("accessRole")}
        for item in listing
        if not item.get("hidden")
    ]


def _resolve_calendar(value):
    """A calendar id from an id or a name ('school'). Nothing given means the user's main calendar."""
    if not value or str(value).strip().lower() in {"primary", "main", "my calendar", "default"}:
        return {"id": "primary", "name": "Primary"}
    calendars = _calendars()
    wanted = str(value).strip().lower()
    exact = [c for c in calendars if c["id"].lower() == wanted or c["name"].lower() == wanted]
    matches = exact or [c for c in calendars if wanted in c["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    names = ", ".join(c["name"] for c in (matches or calendars))
    raise GoogleError(f"{'Several calendars match' if matches else 'No calendar matches'} '{value}'. Calendars: {names}.")


def _find_event(event_id, calendar):
    """The calendar an event lives on, and the event. With no calendar named, the main one is tried and then the rest."""
    if calendar:
        found = _resolve_calendar(calendar)
        return found, api("GET", f"{BASE}/calendars/{_path(found['id'])}/events/{event_id}")
    try:
        return {"id": "primary", "name": "Primary"}, api("GET", f"{BASE}/calendars/primary/events/{event_id}")
    except GoogleError:
        pass
    for other in _calendars():
        if other["primary"]:
            continue
        try:
            return other, api("GET", f"{BASE}/calendars/{_path(other['id'])}/events/{event_id}")
        except GoogleError:
            continue
    raise GoogleError("Couldn't find that event on any of your calendars.")


def _times(start, end, duration_minutes, all_day):
    if all_day:
        first = _local(start).date()
        last = _local(end).date() if end else first
        # Google's all-day end date is exclusive
        return {"date": first.isoformat()}, {"date": (last + timedelta(days=1)).isoformat()}
    begin = _local(start)
    finish = _local(end) if end else begin + timedelta(minutes=int(duration_minutes or 60))
    return {"dateTime": begin.isoformat()}, {"dateTime": finish.isoformat()}


def _moved(current, start, end, duration_minutes):
    """New start and end for an existing event. A new start alone moves it, keeping its length."""
    if "date" in current["start"]:
        old_first = datetime.fromisoformat(current["start"]["date"]).date()
        old_after_last = datetime.fromisoformat(current["end"]["date"]).date()
        first = _local(start).date() if start else old_first
        after_last = _local(end).date() + timedelta(days=1) if end else first + (old_after_last - old_first)
        return {"date": first.isoformat()}, {"date": after_last.isoformat()}

    old_start = datetime.fromisoformat(current["start"]["dateTime"].replace("Z", "+00:00"))
    old_end = datetime.fromisoformat(current["end"]["dateTime"].replace("Z", "+00:00"))
    begin = _local(start) if start else old_start.astimezone()
    if end:
        finish = _local(end)
    elif duration_minutes:
        finish = begin + timedelta(minutes=int(duration_minutes))
    else:
        finish = begin + (old_end - old_start)
    if finish <= begin:
        raise GoogleError("The event would end before it starts.")
    return {"dateTime": begin.isoformat()}, {"dateTime": finish.isoformat()}


# ---------------------------------------------------------------------------------------------- the tools

@safe
def calendar_list_events(days=7, query=None, start=None, calendar=None, limit=50):
    """Events from every calendar the user has (or just one), from now or `start` over the next `days` days, soonest first."""
    begin = _local(start) if start else datetime.now().astimezone()
    params = {
        "timeMin": begin.isoformat(),
        "timeMax": (begin + timedelta(days=max(1, min(int(days), 730)))).isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": 250,
    }
    if query:
        params["q"] = query
    limit = max(1, min(int(limit), 250))
    calendars = [_resolve_calendar(calendar)] if calendar else _calendars()
    skipped = []

    def fetch(cal):
        try:
            return cal, api("GET", f"{BASE}/calendars/{_path(cal['id'])}/events", params=params).get("items", [])
        except GoogleError as error:
            skipped.append(f"{cal['name']} ({error})")
            return cal, []

    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(fetch, calendars))

    events = [(raw, cal) for cal, items in fetched for raw in items if raw.get("status") != "cancelled" and raw.get("start")]
    events.sort(key=lambda pair: _starts_at(pair[0]))
    result = {
        "calendars_checked": [cal["name"] for cal in calendars],
        "count": min(len(events), limit),
        "events": [_event(raw, cal) for raw, cal in events[:limit]],
    }
    if len(events) > limit:
        result["more"] = f"{len(events) - limit} more events after these. Raise limit, or ask for a shorter stretch of days."
    if skipped:
        result["couldnt_read"] = skipped
    return result


@safe
def calendar_create_event(title, start, end=None, duration_minutes=60, all_day=False, location=None, description=None, attendees=None, calendar=None):
    """Adds an event (to the main calendar unless `calendar` names another). Inviting people emails them, so that asks first."""
    target = _resolve_calendar(calendar)
    attendees = [a.strip() for a in (attendees or []) if a.strip()]
    first, last = _times(start, end, duration_minutes, all_day)
    if attendees:
        if not approve(
            f"Create this event and email invitations?\n\n    {title}\n    When: {_show(first)}\n    Invite: {', '.join(attendees)}\n",
            f"Shall I create {title} and send invitations to {', '.join(attendees)}?",
        ):
            return declined()
    body = {"summary": title, "start": first, "end": last}
    if location:
        body["location"] = location
    if description:
        body["description"] = description
    if attendees:
        body["attendees"] = [{"email": email} for email in attendees]
    event = api("POST", f"{BASE}/calendars/{_path(target['id'])}/events", params={"sendUpdates": "all" if attendees else "none"}, body=body)
    return {"created": True, **_event(event, target)}


@safe
def calendar_update_event(event_id, title=None, start=None, end=None, duration_minutes=None, location=None, description=None, add_attendees=None, calendar=None):
    """Changes an event: its title, time, place, notes, or who's invited. Only what you give is changed."""
    target, current = _find_event(event_id, calendar)
    body = {}
    if title:
        body["summary"] = title
    if location is not None:
        body["location"] = location
    if description is not None:
        body["description"] = description
    if start or end or duration_minutes:
        body["start"], body["end"] = _moved(current, start, end, duration_minutes)
    new_people = [a.strip() for a in (add_attendees or []) if a.strip()]
    if new_people:
        existing = [{"email": a["email"]} for a in current.get("attendees", [])]
        body["attendees"] = existing + [{"email": email} for email in new_people if email not in {a["email"] for a in existing}]
        if not approve(
            f"Update '{current.get('summary', 'this event')}' and email invitations?\n\n    Invite: {', '.join(new_people)}\n",
            f"Shall I invite {', '.join(new_people)} to {current.get('summary', 'this event')}?",
        ):
            return declined()
    if not body:
        return {"error": "Nothing to change. Give a new title, time, location, description, or people to invite."}
    event = api("PATCH", f"{BASE}/calendars/{_path(target['id'])}/events/{event_id}", params={"sendUpdates": "all" if new_people else "none"}, body=body)
    return {"updated": True, **_event(event, target)}


@safe
def calendar_delete_event(event_id, calendar=None):
    """Deletes an event (and tells the guests it's cancelled, if it has any), after the user approves."""
    target, raw = _find_event(event_id, calendar)
    event = _event(raw, target)
    guests = event.get("attendees", [])
    note = f"\n    Guests will be told it's cancelled: {', '.join(guests)}" if guests else ""
    if not approve(
        f"Delete this event?\n\n    {event['title']}\n    {event['start']}\n    Calendar: {target['name']}{note}\n",
        f"Shall I delete {event['title']} on {event['start']}?" + (" The guests will be told it's cancelled." if guests else ""),
    ):
        return declined()
    api("DELETE", f"{BASE}/calendars/{_path(target['id'])}/events/{event_id}", params={"sendUpdates": "all" if guests else "none"})
    return {"deleted": True, "title": event["title"], "start": event["start"], "calendar": target["name"]}
