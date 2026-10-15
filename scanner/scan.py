"""Conservative public-website scanner. Signals are hints, never confirmed availability."""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
HEADERS = {"User-Agent": "MarathonEntryWatch/0.1 (+public event monitoring; contact via GitHub repository)", "Accept-Language": "en-AU,en;q=0.8"}
OPEN = re.compile(r"\b(?:register now|entries (?:are )?open|registration (?:is )?open|enter now|apply for (?:the )?ballot|ballot (?:is )?open)\b", re.I)
CLOSED = re.compile(r"\b(?:entries (?:are )?closed|registration (?:is )?closed|ballot (?:is )?closed|sold out|entries (?:have )?sold out)\b", re.I)

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default

def check(race):
    result = {**race, "checked_at": NOW, "status": "unknown", "http_status": None, "evidence": "", "error": ""}
    try:
        r = requests.get(race["official_url"], headers=HEADERS, timeout=18)
        result["http_status"] = r.status_code
        r.raise_for_status()
        if "html" not in r.headers.get("Content-Type", "text/html").lower():
            result["error"] = "Not an HTML page"
            return result
        soup = BeautifulSoup(r.text[:1500000], "html.parser")
        for tag in soup(["script", "style", "footer", "nav", "noscript"]):
            tag.decompose()
        text = " ".join(soup.stripped_strings)
        match_open = OPEN.search(text)
        match_closed = CLOSED.search(text)
        if match_open and match_closed:
            result["status"] = "conflicting_signals"
            result["evidence"] = f"Open: {match_open.group(0)}; closed: {match_closed.group(0)}"
        elif match_open:
            result["status"] = "possible_open"
            result["evidence"] = match_open.group(0)
        elif match_closed:
            result["status"] = "possible_closed"
            result["evidence"] = match_closed.group(0)
        else:
            result["status"] = "no_signal"
    except requests.RequestException as exc:
        result["error"] = str(exc)[:200]
    return result

def main():
    DATA.mkdir(exist_ok=True)
    races = load_json(ROOT / "races.json", [])
    previous = {v["id"]: v for v in load_json(DATA / "races.json", {}).get("races", [])}
    history = load_json(DATA / "history.json", [])
    results = [check(r) for r in races]
    for race in results:
        old = previous.get(race["id"])
        if old and old.get("status") != race["status"]:
            history.append({"at": NOW, "id": race["id"], "name": race["name"], "before": old.get("status"), "after": race["status"]})
    history = history[-500:]
    payload = {"generated_at": NOW, "disclaimer": "Automated text signals only; always verify eligibility, distance and entry window on the official site.", "races": results}
    (DATA / "races.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Checked {len(results)} races; {sum(r['status']=='possible_open' for r in results)} possible-open signals")
    return 0

if __name__ == "__main__":
    sys.exit(main())
