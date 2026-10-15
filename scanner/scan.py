"""Check configured event or registration URLs. Never infer dates from generic HTML text."""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from enrich import extract, linked_registration_page, merge_detected
from datetime import datetime, date, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
HEADERS = {"User-Agent":"MarathonEntryWatch/0.2 (public race page monitoring)","Accept-Language":"en-AU,en;q=0.8,ja;q=0.6"}
OPEN = re.compile(r"(?:\b(?:register now|register today|entries (?:are )?open|registrations? (?:are |is )?open|entries open now|entry (?:is )?open|enter now|book now|secure your spot|ballot (?:is )?open|2027 entries open)\b|エントリー受付中|申込受付中|抽選申込受付中|エントリー開始|申し込み受付中)", re.I)
CLOSED = re.compile(r"(?:\b(?:entries (?:are )?closed|registrations? (?:are |is )?closed|ballot (?:is )?closed|sold out|entries close)\b|受付終了|募集終了|定員に達しました)", re.I)

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default

def date_status(race):
    start, end = race.get("entry_open_date"), race.get("entry_close_date")
    if not start and not end:
        return "dates_unknown"
    today = date.today().isoformat()
    if start and today < start:
        return "scheduled"
    if end and today > end:
        return "window_ended"
    if start and end and start <= today <= end:
        return "within_published_window"
    return "partial_window"

def check(session, race):
    target = race.get("registration_url") or race["official_url"]
    result = {**race, "checked_at":NOW,"status":"unknown","http_status":None,
              "evidence":"","error":"","checked_url":target,"date_window_status":date_status(race)}
    # Generic text hints are deliberately not treated as confirmed availability.
    # The race configuration may provide verified edition-specific entry windows.
    try:
        resp = session.get(target,headers=HEADERS,timeout=12)
        result["http_status"] = resp.status_code
        resp.raise_for_status()
        if "html" not in resp.headers.get("Content-Type", "text/html").lower():
            result["error"]="Non-HTML response"
            return result
        soup = BeautifulSoup(resp.text[:1200000],"html.parser")
        for tag in soup(["script","style","footer","nav","noscript"]):
            tag.decompose()
        detected, parsed_soup = extract(resp.text, resp.url, race)
        result["detected"] = detected
        result["scanned_pages"] = [resp.url]
        txt = " ".join(soup.stripped_strings)
        op, cl = OPEN.search(txt), CLOSED.search(txt)
        if op and cl:
            result["status"]="conflicting_signals"
            result["evidence"]=f"Open: {op.group(0)}; closed: {cl.group(0)}"
        elif op:
            result["status"]="possible_open"
            result["evidence"]=op.group(0)
        elif cl:
            result["status"]="possible_closed"
            result["evidence"]=cl.group(0)
        else:
            result["status"]="no_signal"
        # Follow at most one same-host entry or information page. It can
        # supply candidate dates/fees but must not override verified fields.
        if not race.get("registration_page_verified"):
            linked = linked_registration_page(parsed_soup, resp.url)
            if linked and linked != resp.url:
                try:
                    secondary = session.get(linked, headers=HEADERS, timeout=10)
                    secondary.raise_for_status()
                    if "html" in secondary.headers.get("Content-Type", "text/html").lower():
                        extra, _ = extract(secondary.text, secondary.url, race)
                        result["detected"] = merge_detected(result["detected"], extra)
                        result["scanned_pages"].append(secondary.url)
                        more_text = BeautifulSoup(secondary.text[:900000], "html.parser")
                        for tag in more_text(["script","style","footer","nav","noscript"]):
                            tag.decompose()
                        if result["status"] == "no_signal":
                            op2, cl2 = OPEN.search(" ".join(more_text.stripped_strings)), CLOSED.search(" ".join(more_text.stripped_strings))
                            if op2 and not cl2:
                                result["status"]="possible_open"
                                result["evidence"]="Linked entry page: "+op2.group(0)
                            elif cl2 and not op2:
                                result["status"]="possible_closed"
                                result["evidence"]="Linked entry page: "+cl2.group(0)
                except requests.RequestException:
                    pass
    except requests.RequestException as exc:
        result["error"]=str(exc)[:200]
        result["status"]="unknown"
    # Verified organiser evidence takes precedence over generic site-text hints.
    # A closed published window must never remain "open" because of stale text.
    verified = race.get("verified_entry_status")
    checked_on = race.get("status_verified_at")
    if verified == "open" and checked_on:
        age = (date.today() - date.fromisoformat(checked_on)).days
        if race.get("entry_close_date") and date.today().isoformat() > race["entry_close_date"]:
            result["status"] = "window_ended"
            result["evidence"] = "Verified application deadline has passed"
        elif age <= 14:
            result["status"] = "confirmed_open"
            result["evidence"] = "Organiser verified on " + checked_on
        elif result["status"] not in ("possible_open", "possible_closed"):
            result["status"] = "unknown"
            result["evidence"] = "Previously verified open; verification is stale"
    # A published date window is distinct from site-text hints.
    # It is never silently converted into a confirmed live entry status.
    result["registration_evidence_status"] = result["status"]
    return result

def main():
    DATA.mkdir(exist_ok=True)
    races=load(ROOT/"races.json",[])
    previous={r["id"]:r for r in load(DATA/"races.json",{}).get("races",[])}
    history=load(DATA/"history.json",[])
    # Bound parallelism keeps a growing race list from taking hours to scan.
    # Use an independent session per request; Session is not thread-safe.
    def scan_one(race):
        with requests.Session() as session:
            return check(session, race)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(scan_one, races))
    for r in results:
        old=previous.get(r["id"])
        if old and any(old.get(k)!=r.get(k) for k in ("status","entry_open_date","entry_close_date","race_date")):
            history.append({"at":NOW,"id":r["id"],"name":r["name"],"before":old.get("status"),"after":r["status"],"dates_changed":any(old.get(k)!=r.get(k) for k in ("entry_open_date","entry_close_date","race_date"))})
    (DATA/"races.json").write_text(json.dumps({"generated_at":NOW,"disclaimer":"Dates are only shown when explicitly verified and recorded. Automated text detection is not a confirmation of current entry eligibility.", "races":results},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (DATA/"history.json").write_text(json.dumps(history[-500:],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Checked {len(results)} race sites")
    return 0

if __name__=="__main__":
    sys.exit(main())
