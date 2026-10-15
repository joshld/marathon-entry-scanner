"""Regression checks for the location taxonomy and dashboard controls."""
import json
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONTINENTS = {"Oceania", "Asia", "Europe", "North America", "Africa", "South America"}
EXPECTED = {
    "sydney-marathon": ("Australia", "Oceania"),
    "tokyo": ("Japan", "Asia"),
    "london-marathon": ("United Kingdom", "Europe"),
    "berlin-marathon": ("Germany", "Europe"),
    "paris-marathon": ("France", "Europe"),
    "chicago-marathon": ("United States", "North America"),
    "comrades-marathon": ("South Africa", "Africa"),
    "utmb-mont-blanc": ("France", "Europe"),
    "singapore-marathon": ("Singapore", "Asia"),
    "vancouver-marathon": ("Canada", "North America"),
    "reykjavik-marathon": ("Iceland", "Europe"),
    "bergen-city-marathon": ("Norway", "Europe"),
    "rio-de-janeiro-marathon": ("Brazil", "South America"),
    "santiago-marathon": ("Chile", "South America"),
    "buenos-aires-marathon": ("Argentina", "South America"),
    "cape-town-marathon": ("South Africa", "Africa"),
    "nairobi-marathon": ("Kenya", "Africa"),
    "tata-mumbai-marathon": ("India", "Asia"),
    "beijing-marathon": ("China", "Asia"),
    "dubai-marathon": ("United Arab Emirates", "Asia"),
    "tarawera-ultra-trail": ("New Zealand", "Oceania"),
    "run-larapinta": ("Australia", "Oceania"),
}

class CatalogAndDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.races = json.loads((ROOT / "races.json").read_text(encoding="utf-8"))
        cls.page = BeautifulSoup((ROOT / "site/index.html").read_text(encoding="utf-8"), "html.parser")
        cls.script = cls.page.find("script").get_text()

    def test_catalog_has_unique_ids_and_locations(self):
        self.assertGreaterEqual(len(self.races), 207)
        new_ids=["rio-de-janeiro-marathon","santiago-marathon","buenos-aires-marathon","cape-town-marathon","two-oceans-marathon","nairobi-marathon","tata-mumbai-marathon","new-delhi-marathon","beijing-marathon","ultra-trail-kosciuszko","surf-coast-century","blackall100","prague-half-marathon","roma-ostia-half-marathon","zegama-aizkorri","marathon-du-medoc","dubai-marathon","javelina-jundred","tarawera-ultra-trail","run-larapinta"]
        self.assertTrue(set(new_ids).issubset({race["id"] for race in self.races}))
        self.assertEqual(len({r["id"] for r in self.races}), len(self.races))
        for race in self.races:
            self.assertIn(race["continent"], CONTINENTS, race["name"])
            self.assertNotIn(race["country"], {"Europe","Other","International Ultra",""}, race["name"])
            self.assertTrue(race["city"], race["name"])
            self.assertTrue(race["registration_url"].startswith("https://"), race["name"])

    def test_added_race_metadata_is_honest(self):
        new_ids=["rio-de-janeiro-marathon","santiago-marathon","buenos-aires-marathon","cape-town-marathon","two-oceans-marathon","nairobi-marathon","tata-mumbai-marathon","new-delhi-marathon","beijing-marathon","ultra-trail-kosciuszko","surf-coast-century","blackall100","prague-half-marathon","roma-ostia-half-marathon","zegama-aizkorri","marathon-du-medoc","dubai-marathon","javelina-jundred","tarawera-ultra-trail","run-larapinta"]
        tracked={race["id"]:race for race in self.races}
        for key in new_ids:
            race=tracked[key]
            self.assertTrue(race["official_url"].startswith("https://"),key)
            self.assertTrue(race["registration_url"].startswith("https://"),key)
            self.assertTrue(set(race["distance"]).issubset({"Marathon","Half marathon","Ultra"}),key)
            if race.get("race_date"):
                self.assertTrue(race.get("date_source"),key)
            if race.get("verified_entry_status"):
                self.assertTrue(race.get("status_source_url"),key)
                self.assertTrue(race.get("status_verified_at"),key)
        self.assertIsNone(tracked["buenos-aires-marathon"]["race_date"])
        self.assertIn("Four separate stages",tracked["run-larapinta"]["race_date_note"])
        self.assertIn("ballot",tracked["run-larapinta"]["entry_notes"].lower())

    def test_osaka_2027_dates_and_working_government_source(self):
        by_id = {r["id"]: r for r in self.races}
        osaka = by_id["osaka"]
        self.assertEqual(osaka["race_date"], "2027-02-28")
        self.assertEqual(osaka["entry_open_date"], "2026-07-28")
        self.assertEqual(osaka["entry_close_date"], "2026-08-28")
        self.assertEqual(osaka["date_verified_at"], "2026-10-15")
        self.assertIn("city.osaka.lg.jp", osaka["registration_url"])
        self.assertEqual(osaka["registration_url"], osaka["date_source"])
        self.assertNotIn("osaka-marathon.com", osaka["registration_url"])
        self.assertIn("charity", osaka["entry_notes"].lower())
        self.assertIn("general ballot", osaka["entry_notes"].lower())
        self.assertGreater(len(osaka["entry_options"]), 0)

    def test_osaka_2027_has_confirmed_date_and_live_official_source(self):
        by_id={r["id"]:r for r in self.races}
        race=by_id["osaka"]
        self.assertEqual(race["race_date"],"2027-02-28")
        self.assertEqual(race["entry_open_date"],"2026-07-28")
        self.assertEqual(race["entry_close_date"],"2026-08-28")
        self.assertTrue(race["date_source"].startswith("https://www.city.osaka.lg.jp/"))
        self.assertEqual(race["registration_url"],race["date_source"])
        self.assertEqual(race["official_url"],race["date_source"])
        self.assertIn("19 October 2026",race["entry_notes"])
        self.assertFalse(race["registration_page_verified"])
        self.assertTrue(race["eligibility"]["source_url"])

    def test_known_country_continent_mapping(self):
        by_id = {r["id"]: r for r in self.races}
        for event_id, (country, continent) in EXPECTED.items():
            with self.subTest(event=event_id):
                self.assertEqual(by_id[event_id]["country"], country)
                self.assertEqual(by_id[event_id]["continent"], continent)

    def test_dashboard_has_nested_location_controls(self):
        location = self.page.select_one("details#country-filter")
        self.assertIsNotNone(location)
        self.assertEqual(location.select_one("summary")["id"], "country-summary")
        self.assertIsNotNone(location.select_one("#country-options"))
        for fragment in ("buildLocationFilter", "syncLocationGroups", "locationSummary", "continent-checkbox",
                         "data-expand-continent", "countryContinents", "No locations", "All locations"):
            self.assertIn(fragment, self.script)

    def test_mobile_menus_do_not_overlap_later_filters(self):
        # Menus are overlays on desktop but expand in normal flow on mobile.
        # This is important for touch access to nested continent/country lists.
        css = self.page.find("style").get_text()
        self.assertIn(".distance-filter[open]{z-index:100}", css)
        self.assertIn("@media (max-width:700px)", css)
        self.assertIn(".filters .distance-filter .distance-menu{", css)
        self.assertIn("position:static;", css)
        self.assertIn("overflow-y:auto;", css)
        self.assertIn("max-height:min(55vh,420px)", css)

    def test_expanded_scope_heading(self):
        self.assertIn("Marathons · Half Marathons · Ultras · Worldwide", str(self.page))
        self.assertIn('"Canada":"North America"', self.script)
        self.assertIn('"Norway":"Europe"', self.script)

    def test_capped_accessible_open_entry_ticker(self):
        banner = self.page.select_one("section#open-ticker")
        self.assertIsNotNone(banner)
        self.assertIsNotNone(banner.select_one("#ticker-track"))
        for fragment in ("OPEN_TICKER_LIMIT = 6", 'r.status==="confirmed_open"',
                         "verifiedOpenCandidates", "renderOpenTicker", "aria-hidden",
                         'tabindex="-1"', "r.entry_open_date"):
            self.assertIn(fragment, self.script)
        ticker_script=self.script.split("function renderOpenTicker(){",1)[1].split("const statuses=",1)[0]
        # Tiles (and scrolling clones) must open the existing in-page race card,
        # never launch the organiser website in another tab.
        self.assertIn('data-ticker-race-id', ticker_script)
        self.assertIn('const target="#race-"+encodeURIComponent(r.id)', ticker_script)
        self.assertIn("revealRaceCard(tile.dataset.tickerRaceId)", ticker_script)
        self.assertIn("event.preventDefault()", ticker_script)
        self.assertNotIn("target=\"_blank\"", ticker_script)
        self.assertNotIn("r.registration_url||r.official_url", ticker_script)
        css = self.page.find("style").get_text()
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn(".ticker-window:hover .ticker-track", css)
        self.assertIn("overflow-x:auto", css)

    def test_existing_filters_and_date_range_preserved(self):
        for item in ("#distance-filter", "#type-filter", "#status-filter", "#date-from", "#date-to", "#include-undated"):
            self.assertIsNotNone(self.page.select_one(item), item)


if __name__ == "__main__":
    unittest.main()
