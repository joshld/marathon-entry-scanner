import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scanner"))
from enrich import iso_date, event_match, extract, linked_registration_page, merge_detected


RACE = {"name": "Example City Marathon", "country": "Australia"}


class EnrichmentTests(unittest.TestCase):
    def test_supported_dates(self):
        self.assertEqual(iso_date("Sunday 18th April 2027"), "2027-04-18")
        self.assertEqual(iso_date("20 Apr 2026"), "2026-04-20")
        self.assertEqual(iso_date("April 18, 2027"), "2027-04-18")
        self.assertEqual(iso_date("2027年7月4日"), "2027-07-04")
        self.assertEqual(iso_date("2027-04-18T08:00:00Z"), "2027-04-18")
        self.assertIsNone(iso_date("2025-04-18"))
        self.assertIsNone(iso_date("2027-02-30"))

    def test_event_names_not_unrelated(self):
        self.assertTrue(event_match("Example City Marathon 2027", RACE))
        self.assertFalse(event_match("Another Trail Run 2027", RACE))

    def test_matching_jsonld_event(self):
        html = """<html><script type="application/ld+json">
        {"@type":"SportsEvent","name":"Example City Marathon 2027",
        "startDate":"2027-06-06T06:00:00+10:00",
        "offers":{"@type":"Offer","price":"185","priceCurrency":"AUD",
        "validFrom":"2026-10-01","validThrough":"2027-05-25"}}
        </script><body>Welcome</body></html>"""
        detected, soup = extract(html, "https://example.org/enter", RACE)
        self.assertEqual(detected["race_date"]["value"], "2027-06-06")
        self.assertEqual(detected["entry_open_date"]["value"], "2026-10-01")
        self.assertEqual(detected["entry_close_date"]["value"], "2027-05-25")
        self.assertEqual(detected["prices"][0]["text"], "AUD 185")
        self.assertEqual(detected["race_date"]["verification"], "unverified")

    def test_no_unrelated_event_date(self):
        html = """<script type="application/ld+json">
        {"@type":"Event","name":"Festival of Music","startDate":"2027-04-03"}
        </script><body>Recent article 3 April 2027</body>"""
        found, _ = extract(html, "https://example.org", RACE)
        self.assertNotIn("race_date", found)

    def test_explicit_text_entry_window_and_fee(self):
        html = """<h1>Example City Marathon</h1><p>Race date: Sunday 18th April 2027</p>
        <p>Entries open: 20 April 2026</p><p>Entries close: 1 March 2027</p>
        <p>Entry fee A$220.</p><p>Minimum age: 18 years.</p>"""
        found, _ = extract(html, "https://example.org", RACE)
        self.assertEqual(found["race_date"]["value"], "2027-04-18")
        self.assertEqual(found["entry_open_date"]["value"], "2026-04-20")
        self.assertEqual(found["entry_close_date"]["value"], "2027-03-01")
        self.assertTrue(found.get("prices"))
        self.assertTrue(found.get("restrictions"))

    def test_link_stays_on_official_host(self):
        html = """<a href="/register">Register now</a>
        <a href="https://unknown-payments.test/pay">Enter here</a>"""
        _, soup = extract(html, "https://example.org", RACE)
        self.assertEqual(linked_registration_page(soup, "https://example.org"), "https://example.org/register")

    def test_merge_keeps_primary_date(self):
        p = {"race_date": {"value":"2027-04-01"}}
        s = {"race_date":{"value":"2027-04-05"}, "prices":[{"text":"AUD 120"}]}
        result=merge_detected(p,s)
        self.assertEqual(result["race_date"]["value"],"2027-04-01")
        self.assertEqual(result["prices"][0]["text"],"AUD 120")


if __name__=="__main__":
    unittest.main()
