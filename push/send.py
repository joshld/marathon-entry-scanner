"""Dispatch native Web Push race alerts without storing device endpoints in GitHub.

Runs after the daily scanner, explicitly disabled unless configured. Subscribe
endpoints + preferences live in Cloudflare KV behind a bearer-protected Worker.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests


def event_matches(event, pref):
    return (
        event.get("type") in pref.get("types", [])
        and event.get("country") in pref.get("countries", [])
        and bool(set(event.get("distance", [])) & set(pref.get("distances", [])))
    )


def eligible_events(events, subscription, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        created = datetime.fromisoformat(subscription["createdAt"])
        sent_at = subscription.get("lastSentAt")
        cutoff = max(
            created,
            datetime.fromisoformat(sent_at) if sent_at else created,
            now - timedelta(days=7),
        )
        if cutoff.tzinfo is None:
            return []
    except (TypeError, KeyError, ValueError):
        return []
    matched = []
    for event in events:
        try:
            when = datetime.fromisoformat(event["at"])
            if when.tzinfo is not None and cutoff < when <= now and event_matches(
                event, subscription["preferences"]
            ):
                matched.append(event)
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(matched, key=lambda event: event["at"], reverse=True)[:10]


def payload_for_events(events):
    first = events[0]
    label = {"open": "Entries open", "soon": "Entries opening soon", "new": "New race added"}
    title = "Race Entry Radar" if len(events) > 1 else first.get("name", "Race Entry Radar")
    body = (
        f"{len(events)} race entry updates matched your preferences."
        if len(events) > 1
        else f"{label.get(first['type'], 'Race update')}: {first.get('name', 'Race')}"
    )
    return json.dumps(
        {
            "title": title[:100],
            "body": body[:220],
            "tag": f"race-updates-{datetime.now(timezone.utc).date().isoformat()}",
            "url": first.get("url") or "https://joshld.github.io/marathon-entry-scanner/",
        },
        ensure_ascii=False,
    )


def worker_request(session,base,secret,method,path,payload=None,params=None):
    response=session.request(
        method,
        base.rstrip("/") + path,
        headers={"Authorization":"Bearer "+secret,"Content-Type":"application/json"},
        json=payload,
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def dispatch(events, *, send=False, session=None, now=None):
    if not send or os.getenv("BROWSER_PUSH_ENABLED","").lower()!="true":
        print("Browser push disabled; nothing sent")
        return 0
    keys=["PUSH_WORKER_URL","PUSH_ADMIN_TOKEN","PUSH_VAPID_PRIVATE"]
    missing=[name for name in keys if not os.getenv(name)]
    if missing:
        print("Browser push unavailable: missing configuration ("+", ".join(missing)+")")
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("Install pywebpush to send browser notifications",file=sys.stderr)
        return 1
    base=os.environ["PUSH_WORKER_URL"]
    parsed=urlparse(base)
    if parsed.scheme!="https" or not parsed.hostname:
        print("Invalid PUSH_WORKER_URL",file=sys.stderr)
        return 1
    token=os.environ["PUSH_ADMIN_TOKEN"]
    vapid=os.environ["PUSH_VAPID_PRIVATE"]
    now=now or datetime.now(timezone.utc)
    max_recipients=100
    sent=0
    errors=0
    cursor=None
    own_session=session or requests.Session()
    try:
        for page in range(100):
            params={"cursor":cursor} if cursor else None
            result=worker_request(own_session,base,token,"GET","/admin/subscribers",params=params)
            for item in result.get("subscribers",[]):
                relevant=eligible_events(events,item,now)
                if not relevant:
                    continue
                if sent>=max_recipients:
                    print("Push send limit reached; remaining devices will retry next scheduled run.")
                    return 0
                try:
                    webpush(
                        subscription_info=item["subscription"],
                        data=payload_for_events(relevant),
                        vapid_private_key=vapid,
                        vapid_claims={"sub":"https://joshld.github.io/marathon-entry-scanner/"},
                        ttl=86400,
                        timeout=15,
                    )
                    worker_request(own_session,base,token,"POST","/admin/ack",{"ids":[item["id"]]})
                    sent+=1
                except (WebPushException,requests.RequestException,KeyError,ValueError):
                    errors+=1
                    # Avoid printing sensitive subscription endpoints.
                    print("Push delivery or acknowledgement failed for one device",file=sys.stderr)
            cursor=result.get("cursor")
            if not cursor:
                break
        else:
            print("Worker subscriber pagination exceeded 100 pages",file=sys.stderr)
            return 1
    except (requests.RequestException,ValueError,KeyError):
        print("Cannot retrieve push subscribers from secure endpoint",file=sys.stderr)
        return 1
    finally:
        if session is None:
            own_session.close()
    print(f"Browser push: {sent} sent; {errors} failed")
    return 1 if errors else 0


if __name__=="__main__":
    from pathlib import Path
    file=Path(__file__).resolve().parents[1]/"data"/"alert-events.json"
    changes=json.loads(file.read_text(encoding="utf-8")) if file.exists() else []
    sys.exit(dispatch(changes,send="--send" in sys.argv))
