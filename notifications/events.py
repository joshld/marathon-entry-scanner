"""Prepare trustworthy, non-personal alert events from successive race scans.

Persist *race events*, never subscriber email addresses, in the public repo.
"""
import json
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENT_FILE = ROOT / "data" / "alert-events.json"

def make_event(kind, race, today):
    return {
        "key": f"{kind}:{race['id']}:{race.get('entry_open_date') or race.get('status_verified_at') or today.isoformat()}",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "type": kind,
        "id": race["id"],
        "name": race["name"],
        "country": race["country"],
        "distance": race["distance"],
        "race_date": race.get("race_date"),
        "entry_open_date": race.get("entry_open_date"),
        "url": race.get("registration_url") or race.get("official_url"),
    }

def events_from_scan(previous, current, old_events, today=None):
    today = today or datetime.now(ZoneInfo("Australia/Brisbane")).date()
    before = {r["id"]: r for r in previous}
    known = {x["key"] for x in old_events}
    new = []
    # No catch-up spam when the system has no comparison baseline.
    first_run = not previous
    for race in current:
        previous_race = before.get(race["id"])
        types = []
        if not first_run and previous_race is None:
            types.append("new")
        # Only organiser-confirmed, not possible_open site-text matches.
        if (previous_race is not None and race.get("status") == "confirmed_open"
            and race.get("verified_entry_status") == "open"
            and previous_race.get("status") != "confirmed_open"):
            types.append("open")
        open_day = race.get("entry_open_date")
        if open_day and race.get("date_source") and race.get("status") != "confirmed_open":
            try:
                days = (date.fromisoformat(open_day) - today).days
                if 0 < days <= 7:
                    types.append("soon")
            except ValueError:
                pass
        for kind in types:
            event = make_event(kind, race, today)
            if event["key"] not in known:
                known.add(event["key"])
                new.append(event)
    cutoff = datetime.now(timezone.utc)-timedelta(days=90)
    kept=[]
    for item in old_events:
        try:
            if datetime.fromisoformat(item["at"]) >= cutoff:
                kept.append(item)
        except (KeyError,ValueError,TypeError):
            pass
    return (kept + new)[-1500:], new

def update_from_files(previous_path, current_path, output_path=EVENT_FILE):
    prev = json.loads(Path(previous_path).read_text()).get("races",[]) if Path(previous_path).exists() else []
    current = json.loads(Path(current_path).read_text()).get("races",[])
    prior = json.loads(Path(output_path).read_text()) if Path(output_path).exists() else []
    all_events, latest = events_from_scan(prev, current, prior)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(all_events,ensure_ascii=False,indent=2)+"\n")
    print(f"Alert events: {len(latest)} new; {len(all_events)} retained")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        sys.exit("usage: python notifications/events.py <previous-races.json> <current-races.json>")
    update_from_files(sys.argv[1],sys.argv[2])
