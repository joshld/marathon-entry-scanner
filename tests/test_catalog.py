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
}

class CatalogAndDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.races = json.loads((ROOT / "races.json").read_text(encoding="utf-8"))
        cls.page = BeautifulSoup((ROOT / "site/index.html").read_text(encoding="utf-8"), "html.parser")
        cls.script = cls.page.find("script").get_text()

    def test_catalog_has_unique_ids_and_locations(self):
        self.assertGreaterEqual(len(self.races), 150)
        self.assertEqual(len({r["id"] for r in self.races}), len(self.races))
        for race in self.races:
            self.assertIn(race["continent"], CONTINENTS, race["name"])
            self.assertNotIn(race["country"], {"Europe","Other","International Ultra",""}, race["name"])
            self.assertTrue(race["city"], race["name"])
            self.assertTrue(race["registration_url"].startswith("https://"), race["name"])

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
        css = self.page.find("style").get_text()
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn(".ticker-window:hover .ticker-track", css)
        self.assertIn("overflow-x:auto", css)

    def test_existing_filters_and_date_range_preserved(self):
        for item in ("#distance-filter", "#type-filter", "#status-filter", "#date-from", "#date-to", "#include-undated"):
            self.assertIsNotNone(self.page.select_one(item), item)


if __name__ == "__main__":
    unittest.main()
