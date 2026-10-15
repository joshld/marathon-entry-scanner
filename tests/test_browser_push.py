"""Tests for browser inbox + optional Web Push, with no live push calls."""
import importlib.util
import os
from pathlib import Path
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("push_sender",ROOT/"push"/"send.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def new_event(at, kind="open", country="Australia", distance=("Marathon",)):
    return {"key":"open:sydney:2027","at":at,"type":kind,
            "country":country,"distance":list(distance),
            "name":"Sydney Marathon","url":"https://example.org"}

def subscriber(created, last=None):
    return {"createdAt":created,"lastSentAt":last,
            "preferences":{"countries":["Australia"],"distances":["Marathon"],
                           "types":["open","soon","new"]},
            "subscription":{"endpoint":"https://fcm.googleapis.com/fcm/send/test",
                            "keys":{"p256dh":"mock","auth":"mock"}}}

class BrowserPushTests(unittest.TestCase):
    def test_only_events_since_device_subscribed(self):
        now=datetime(2026,10,15,10,0,tzinfo=timezone.utc)
        events=[new_event("2026-10-14T08:00:00+00:00"),
                new_event("2026-10-15T09:00:00+00:00")]
        result=module.eligible_events(events,subscriber("2026-10-14T12:00:00+00:00"),now)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["at"],"2026-10-15T09:00:00+00:00")

    def test_last_acknowledgement_prevents_duplicates(self):
        now=datetime(2026,10,15,10,0,tzinfo=timezone.utc)
        item=subscriber("2026-10-12T00:00:00+00:00","2026-10-15T09:30:00+00:00")
        self.assertFalse(module.eligible_events([new_event("2026-10-15T09:00:00+00:00")],item,now))

    def test_country_distance_type_preferences(self):
        item=subscriber("2026-10-13T00:00:00+00:00")
        event=new_event("2026-10-15T08:00:00+00:00")
        self.assertTrue(module.event_matches(event,item["preferences"]))
        self.assertFalse(module.event_matches({**event,"country":"Canada"},item["preferences"]))
        self.assertFalse(module.event_matches({**event,"distance":["Ultra"]},item["preferences"]))
        self.assertFalse(module.event_matches({**event,"type":"unknown"},item["preferences"]))

    def test_missing_credentials_cannot_send(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(module.dispatch([new_event("2026-10-15T09:00:00+00:00")],send=True),0)

    def test_browser_bell_markup_and_accessibility(self):
        html=(ROOT/"site"/"index.html").read_text()
        page=BeautifulSoup(html,"html.parser")
        bell=page.select_one("#updates-toggle")
        self.assertIsNotNone(bell)
        self.assertEqual(bell["aria-controls"],"updates-panel")
        self.assertIsNotNone(page.select_one("#updates-mark-read"))
        self.assertTrue(page.select_one("#updates-panel").has_attr("hidden"))
        self.assertIn("localStorage",html)
        self.assertIn('r.status==="confirmed_open"',html)
        self.assertIn("renderRaceUpdates()",html)
        self.assertNotIn('id="push-controls"',html)
        self.assertNotIn('initBrowserPush()',html)
        self.assertNotIn('Notification.requestPermission()',html)
        self.assertIn('data-race-id="'+ "'+esc(e.id)+'" + '"',html)
        self.assertIn('const target="#race-"+encodeURIComponent(e.id);',html)
        self.assertNotIn('target="_blank" rel="noopener noreferrer"><span class="updates-item-top">',html)
        self.assertIn("revealRaceCard(raceId)",html)
        self.assertIn("raceUpdatesSeen.add(row.dataset.updateKey)",html)
        self.assertIn("card.scrollIntoView(",html)
        self.assertIn("card.focus({preventScroll:true})",html)
        self.assertIn("syncLocationGroups();",html)
        self.assertIn("revealRaceFromHash();",html)

    def test_service_worker_and_disabled_config(self):
        sw=(ROOT/"site"/"push-sw.js").read_text()
        self.assertIn('addEventListener("push"',sw)
        self.assertIn('addEventListener("notificationclick"',sw)
        import json
        cfg=json.loads((ROOT/"site"/"push-config.json").read_text())
        self.assertFalse(cfg["worker_url"])
        self.assertFalse(cfg["vapid_public_key"])
        worker=(ROOT/"push"/"worker.js").read_text()
        self.assertIn("env.PUSH_KV",worker)
        self.assertIn("PUSH_ADMIN_TOKEN",worker)
        self.assertNotIn("BEGIN PRIVATE KEY",worker)

if __name__=="__main__":
    unittest.main()
