"""Email alert regressions; no external email/network operations."""
import importlib.util
import json
import os
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
from notifications.events import events_from_scan
from notifications.dispatch import prefs, matches, select_events, unsubscribe_link, deliver


def race(id="sydney", status="confirmed_open", open_date="2026-10-14"):
    return {"id":id,"name":id.title()+" Marathon","country":"Australia","distance":["Marathon"],
            "status":status,"verified_entry_status":"open",
            "status_verified_at":"2026-10-15","entry_open_date":open_date,
            "entry_close_date":"2026-10-28","race_date":"2027-09-01",
            "date_source":"https://example.org/race","registration_url":"https://example.org/enter"}


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.today=date(2026,10,15)

    def test_first_scan_does_not_mass_notify_new_races(self):
        all_events,new=events_from_scan([], [race()], [], self.today)
        self.assertEqual((all_events,new),([],[]))

    def test_new_race_detected_once(self):
        prev=[race(id="old")]
        latest=prev+[race(id="new",status="possible_open")]
        all_events,new=events_from_scan(prev,latest,[],self.today)
        self.assertEqual([(e["id"],e["type"]) for e in new],[("new","new")])
        second,duplicate=events_from_scan(prev,latest,all_events,self.today)
        self.assertFalse(duplicate)

    def test_open_alert_requires_confirmed_status_and_real_transition(self):
        previously=[race(status="no_signal"),race("possible",status="possible_open")]
        current=[race(),race("possible",status="possible_open")]
        events,new=events_from_scan(previously,current,[],self.today)
        self.assertEqual([(e["id"],e["type"]) for e in new],[("sydney","open")])

    def test_open_alert_does_not_trigger_without_organiser_verification(self):
        old=race(status="unknown")
        current=race(status="confirmed_open")
        current.pop("verified_entry_status")
        _,new=events_from_scan([old],[current],[],self.today)
        self.assertEqual(new,[])

    def test_soon_alert_based_on_published_dates_only_and_deduplicated(self):
        upcoming=race("soon","no_signal","2026-10-20")
        prev=race("other","no_signal","2026-08-20")
        all_events,new=events_from_scan([prev],[prev,upcoming],[],self.today)
        self.assertEqual({x["type"] for x in new},{"soon","new"})
        again,additional=events_from_scan([prev],[prev,upcoming],all_events,self.today)
        self.assertFalse(additional)

    def test_preferences_match_country_distance_and_type(self):
        p=prefs('{"c":["AU","JP"],"d":["H","M"],"a":["open","soon"],"f":"weekly"}')
        self.assertIsNotNone(p)
        event={"type":"open","country":"Australia","distance":["Marathon"]}
        self.assertTrue(matches(event,p))
        self.assertFalse(matches({**event,"country":"Canada"},p))
        self.assertFalse(matches({**event,"distance":["Ultra"]},p))
        self.assertFalse(matches({**event,"type":"new"},p))
        self.assertIsNone(prefs('{"f":"weekly","c":"*","d":[],"a":["open"]}'))

    def test_weekly_and_daily_delivery_window(self):
        e={"at":"2026-10-12T03:00:00+00:00","type":"open","country":"Australia",
           "distance":["Marathon"]}
        p={"c":"*","d":["M"],"a":["open"],"f":"weekly"}
        self.assertEqual(len(select_events([e],p,None,date(2026,10,19))),1)
        self.assertEqual(select_events([e],p,None,date(2026,10,20)),[])
        self.assertEqual(select_events([e],p,"2026-10-19",date(2026,10,19)),[])
        self.assertEqual(select_events([e],{**p,"f":"daily"},None,date(2026,10,19)),[])

    def test_unsubscribe_link_is_hmac_signed(self):
        url=unsubscribe_link("Subscriber@Example.com","https://alerts.example.workers.dev","a-secret")
        self.assertIn("/unsubscribe?",url)
        self.assertIn("s=",url)
        self.assertNotIn("Subscriber@Example.com",url)

    def test_no_config_means_no_network_or_delivery(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(deliver([{"type":"open"}],self.today,dry_run=False),0)


class SignupPanelTests(unittest.TestCase):
    def test_signup_is_disabled_without_provider_configuration(self):
        cfg=json.loads((ROOT/"site"/"alerts-config.json").read_text())
        self.assertFalse(cfg.get("subscription_api_url"))
        self.assertFalse(cfg.get("turnstile_site_key"))
        index=(ROOT/"site"/"index.html").read_text()
        self.assertIn('id="alerts-fields" disabled',index)
        self.assertIn('id="alerts-panel" hidden',index)
        self.assertIn(".alerts-panel[hidden]{display:none!important}",index)
        self.assertIn("initAlertSignup()",index)
        self.assertIn('id="alerts-consent"',index)

    def test_no_secrets_committed(self):
        worker=(ROOT/"subscriptions"/"worker.js").read_text()
        self.assertIn("env.BREVO_API_KEY",worker)
        self.assertNotIn("xkeysib-",worker)
        dispatch=(ROOT/"notifications"/"dispatch.py").read_text()
        self.assertIn("EMAIL_ALERTS_ENABLED",dispatch)


if __name__=="__main__":
    unittest.main()
