"""Personalised Brevo race alert digest (opt-in only).

No live sending unless --send AND EMAIL_ALERTS_ENABLED=true AND secrets exist.
Never log subscriber addresses or store them in the public repository.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlencode
import requests

ROOT=Path(__file__).resolve().parents[1]
API="https://api.brevo.com/v3"
COUNTRIES={
 "Australia":"AU","New Zealand":"NZ","Japan":"JP","Hong Kong":"HK","Taiwan":"TW",
 "South Korea":"KR","Indonesia":"ID","Thailand":"TH","Malaysia":"MY","Vietnam":"VN",
 "Philippines":"PH","Singapore":"SG","United Kingdom":"GB","France":"FR",
 "Germany":"DE","Netherlands":"NL","Spain":"ES","Italy":"IT","Austria":"AT",
 "Denmark":"DK","Czechia":"CZ","Sweden":"SE","Greece":"GR","Portugal":"PT",
 "Switzerland":"CH","Finland":"FI","Ireland":"IE","Norway":"NO","Iceland":"IS",
 "United States":"US","Canada":"CA","South Africa":"ZA"
}
DISTANCES={"Marathon":"M","Half marathon":"H","Ultra":"U"}

def prefs(raw):
    try:
        obj=json.loads(raw)
        if obj["f"] not in ("daily","weekly"):return None
        if not isinstance(obj["d"],list) or not set(obj["d"]) <= {"M","H","U"} or not obj["d"]:return None
        if not isinstance(obj["a"],list) or not set(obj["a"]) <= {"open","soon","new"} or not obj["a"]:return None
        if obj["c"] != "*" and (not isinstance(obj["c"],list) or not obj["c"] or any(
                not isinstance(c,str) or len(c)!=2 for c in obj["c"])):return None
        return obj
    except (KeyError,ValueError,TypeError):
        return None

def matches(event, preference):
    if event["type"] not in preference["a"]:return False
    if preference["c"]!="*" and COUNTRIES.get(event["country"]) not in preference["c"]:return False
    return bool(set(preference["d"]) & {DISTANCES.get(v) for v in event["distance"]})

def select_events(events, preference, last_sent, today):
    if preference["f"]=="weekly" and today.weekday()!=0:return []
    # Catch up missed runs but cap at a week; no unlimited historical blast.
    period=8 if preference["f"]=="weekly" else 2
    cutoff=today-timedelta(days=period)
    if last_sent:
        try:
            last=date.fromisoformat(last_sent)
            if last>=today:return []
            if last>cutoff:cutoff=last
        except ValueError:pass
    out=[]
    for event in events:
        try:
            when=datetime.fromisoformat(event["at"]).astimezone(ZoneInfo("Australia/Brisbane")).date()
        except (ValueError,TypeError,KeyError):
            continue
        if cutoff < when <= today and matches(event,preference):
            out.append(event)
    return out[:25]

def unsubscribe_link(email,base_url,secret):
    email=email.lower().strip()
    encoded=base64.urlsafe_b64encode(email.encode("utf-8")).decode("ascii").rstrip("=")
    sig=hmac.new(secret.encode("utf-8"),email.encode("utf-8"),hashlib.sha256).hexdigest()
    return base_url.rstrip("/")+"/unsubscribe?"+urlencode({"e":encoded,"s":sig})

def message(events,unsubscribe):
    titles={"open":"Entries confirmed open","soon":"Entries opening soon","new":"Newly tracked races"}
    lines=["Race Entry Radar — your personalised race alerts",""]
    for kind in ("open","soon","new"):
        group=[x for x in events if x["type"]==kind]
        if not group:continue
        lines.append(titles[kind])
        for x in group:
            extra=(" · opens "+x["entry_open_date"]) if kind=="soon" and x.get("entry_open_date") else ""
            lines.extend(["• "+x["name"]+" — "+x["country"]+" ("+", ".join(x["distance"])+")"+extra,
                          "  "+x["url"]])
        lines.append("")
    lines.extend(["Registration availability can change or sell out. Check the official page before making travel plans.",
                  "You subscribed to Race Entry Radar updates. Stop these emails:",
                  unsubscribe])
    return "\n".join(lines)

def api(session,method,path,key,data=None,params=None):
    result=session.request(method,API+path,params=params,json=data,timeout=20,
       headers={"api-key":key,"Accept":"application/json",
         **({"Content-Type":"application/json"} if data is not None else {})})
    result.raise_for_status()
    if result.status_code==204:return {}
    return result.json()

def contacts(session,key,list_id):
    for offset in range(0,200000,500):
        page=api(session,"GET",f"/contacts/lists/{list_id}/contacts",key,
          params={"limit":500,"offset":offset})
        items=page.get("contacts",[])
        yield from items
        if len(items)<500:return
    raise RuntimeError("Subscriber list is beyond configured safety limit")

def deliver(events,today,dry_run=True):
    if not events:
        print("No race events to send")
        return 0
    needed=["BREVO_API_KEY","BREVO_LIST_ID","BREVO_SENDER_EMAIL",
            "BREVO_UNSUBSCRIBE_BASE","UNSUBSCRIBE_SECRET"]
    missing=[key for key in needed if not os.getenv(key)]
    if missing:
        print("Email delivery not configured: "+", ".join(missing))
        return 0
    if not dry_run and os.getenv("EMAIL_ALERTS_ENABLED","").lower()!="true":
        print("EMAIL_ALERTS_ENABLED is not true; skipping live delivery")
        return 0
    key=os.environ["BREVO_API_KEY"]
    sender=os.environ["BREVO_SENDER_EMAIL"]
    limit=min(200,max(1,int(os.getenv("EMAIL_ALERTS_SEND_LIMIT","100"))))
    sent=0;eligible=0;fail=0
    with requests.Session() as session:
        for subscriber in contacts(session,key,os.environ["BREVO_LIST_ID"]):
            if subscriber.get("emailBlacklisted") or int(os.environ["BREVO_LIST_ID"]) in subscriber.get("listUnsubscribed",[]):continue
            email=subscriber.get("email","")
            if not email:continue
            pref=prefs((subscriber.get("attributes") or {}).get("RACE_PREFS",""))
            if pref is None:continue
            last_sent=(subscriber.get("attributes") or {}).get("RACE_LAST_SENT","")
            chosen=select_events(events,pref,last_sent,today)
            if not chosen:continue
            eligible+=1
            if dry_run:continue
            if sent>=limit:
                print("Daily safety cap reached; remaining matches were not sent")
                break
            link=unsubscribe_link(email,os.environ["BREVO_UNSUBSCRIBE_BASE"],
                                  os.environ["UNSUBSCRIBE_SECRET"])
            body=message(chosen,link)
            try:
                api(session,"POST","/smtp/email",key,{
                    "sender":{"name":"Race Entry Radar","email":sender},
                    "to":[{"email":email}],
                    "subject":f"Race Entry Radar: {len(chosen)} matching update(s)",
                    "textContent":body,
                    "tags":["race-entry-radar"]
                })
                sent+=1
                # Subscriber-specific delivery state lives only in Brevo.
                # Configure RACE_LAST_SENT as a TEXT contact attribute.
                api(session,"PUT","/contacts/"+requests.utils.quote(email,safe=""),key,{
                    "attributes":{"RACE_LAST_SENT":today.isoformat()}
                })
            except requests.RequestException as exc:
                fail+=1
                print("Email service rejected a send or state update: HTTP/network error",file=sys.stderr)
    print(f"Alert delivery: {eligible} eligible, {sent} sent, {fail} errors"
          +(" (DRY RUN)" if dry_run else ""))
    return 1 if fail else 0

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--send",action="store_true",help="enable sends (still requires EMAIL_ALERTS_ENABLED=true)")
    args=parser.parse_args()
    source=ROOT/"data"/"alert-events.json"
    events=json.loads(source.read_text()) if source.exists() else []
    today=datetime.now(ZoneInfo("Australia/Brisbane")).date()
    return deliver(events,today,dry_run=not args.send)

if __name__=="__main__":
    sys.exit(main())
