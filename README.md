# Race Entry Radar

[Open the dashboard](https://joshld.github.io/marathon-entry-scanner/) · [Run the workflow](https://github.com/joshld/marathon-entry-scanner/actions/workflows/daily.yml)

A GitHub Actions-powered daily worldwide scanner and GitHub Pages dashboard for **marathons (42.2 km), half marathons (21.1 km) and ultramarathons**, with particular attention to Australia and Japan and coverage of Canada, North America, Europe, the Nordic countries, Asia, Oceania and Africa.

The watchlist currently contains **187 events** across Asia, Oceania, Europe, North America and Africa. It can be expanded by editing [`races.json`](races.json).

## Dashboard

The dashboard includes:

- **Entries open banner:** A scrolling shortlist of **up to six** organiser-verified open races appears near the top. Races with a verified entry-opening date are ranked newest first; other confirmed-open races fill remaining spaces, clearly marked with opening date unconfirmed. Clicking a tile opens official registration. The marquee pauses on hover or keyboard focus, and becomes a horizontally swipeable row on mobile / reduced-motion settings. Possible-open text matches are **excluded**.
- **Locations:** One multi-select dropdown grouped by **continent → country**. Select a continent to include all its countries, or use the arrow beside its name to expand the country list and make individual selections. A partially selected continent is shown as partially checked. **Select all** and **Clear** apply to all countries. Multiple continents and countries can be selected at once.
- **Distances:** Multi-select for marathon, half marathon and ultra.
  Multi-stage events such as the Warwick Pentathrun are listed under their actual qualifying race distance (its half-marathon stage), not as a standalone full marathon simply because the stages total 42.2 km.
- **Entry types:** Multi-select for ballot/lottery, direct entry, qualification, charity and unverified/other. A race may match more than one entry type.
- **Entry status:** Multi-select for confirmed open, confirmed closed/sold-out, possible open, closing/closed indicators, conflicting signals and inaccessible websites.
- **Race date range:** Optional inclusive start and end dates. Only **verified** race dates qualify by default; use **Include races without confirmed dates** to include undated events in the date filter.
- Race cards show race dates, entry opening/closing dates, price categories, qualifying restrictions, and links to original sources when available.

The locations selector currently uses these continents: **Oceania, Asia, Europe, North America and Africa**, including Canada within North America and Norway, Sweden, Finland, Denmark and Iceland within Europe. Continent and country names are descriptive geographic fields; ultramarathon is a *distance*, not a geographic category.

## Email subscriptions (optional, not yet active)

**The email subscription panel is temporarily hidden on the public dashboard.** Its code remains available to reactivate later. When enabled, it will appear beneath the Entries Open banner. Visitors can select countries, marathon/half-marathon/ultra distances, alert types (confirmed entries open, published openings within seven days, newly tracked races), and a daily or weekly digest.

**Email signup is deliberately disabled until a secure backend is configured.** No emails are collected by the public dashboard or sent automatically yet.

The planned free-tier architecture is GitHub Actions + a Cloudflare Worker and Turnstile + Brevo double opt-in and mailing lists. Brevo stores subscriber addresses and preferences outside this public repository; the scanner stores only non-personal, deduplicated race events in `data/alert-events.json`. Scheduled sending also requires explicit GitHub Action secrets and `EMAIL_ALERTS_ENABLED=true`. Tentative race-opening signals cannot trigger confirmed-opening emails.

For prerequisites, deployment instructions, consent and unsubscribe testing, see **[Email subscription setup](subscriptions/README.md)**. This must be completed before enabling the form; no secret API keys should ever be committed to GitHub Pages.

## Data format

The manually maintained source is [`races.json`](races.json). Each race has an ID and details such as:

```json
{
  "id": "example-marathon",
  "name": "Example Marathon",
  "city": "Example City",
  "country": "Australia",
  "continent": "Oceania",
  "distance": ["Marathon", "Half marathon"],
  "entry_type": "Ballot",
  "official_url": "https://example.org/",
  "registration_url": "https://example.org/enter",
  "race_date": null,
  "entry_open_date": null,
  "entry_close_date": null,
  "entry_options": [],
  "eligibility": {
    "minimum_age": null,
    "residency": null,
    "qualifying_time": null,
    "other_requirements": [],
    "verification_status": "unverified",
    "source_url": null,
    "verified_at": null
  }
}
```

Set `continent` to the correct region (for example, `Europe`) and `country` to the actual country (for example, `France`). **Do not** use `Europe`, `Other` or `International Ultra` as the country. The location filter groups by `continent` and selects races using `country`.

Set an exact date or entry price only when an organiser source verifies it for the relevant edition, distance and entry category. Store source URLs and verification timestamps. Use `null` when a field isn't known; never derive exact race dates or fees from last year's information.

The scanner writes the latest results to [`data/races.json`](data/races.json) and status changes to [`data/history.json`](data/history.json).

## Scanning and reliability

[`scanner/scan.py`](scanner/scan.py) retrieves each configured race URL and, if identifiable, a relevant same-site registration/information page. [`scanner/enrich.py`](scanner/enrich.py) also looks for structured event metadata and date, fee and eligibility wording.

**Automatically detected information is only a candidate**, displayed as “Possible … · verify” with a source link. Generic text matches are *not* confirmed entry availability: a homepage may describe another year or distance, and some sites require JavaScript or block bot requests. Even a confirmed window can close early when sold out.

The race-date filter uses the explicitly recorded, verified `race_date`, rather than candidate dates, to avoid assigning unrelated calendar dates to an event.

## Setup and deployment

1. Go to **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.
2. Ensure repository Actions permissions allow the workflow to write updated data to the repository.
3. Manually run **Actions → Daily marathon scan and publish → Run workflow** or push relevant source changes to `main`.
4. After the scan and publish jobs succeed, visit <https://joshld.github.io/marathon-entry-scanner/>.

GitHub Actions scans daily at approximately **07:17 Brisbane time** (21:17 UTC). GitHub's scheduled jobs may run late. Push triggers monitor changes under `scanner/`, `site/`, `tests/`, `races.json`, `requirements.txt` and the workflow. Auto-generated `data/` commits do not retrigger the workflow.

The workflow runs Python regression tests before scanning, commits fresh results with conflict retries, and publishes the static dashboard via GitHub Pages.

## Running locally

Requires Python 3.12 or newer.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scanner/scan.py
mkdir -p site/data
cp data/*.json site/data/
python -m http.server 8000 --directory site
```

Open <http://localhost:8000/>.

## Limitations and next steps

Not all monitored registration URLs have been verified individually. Many race dates, entry windows, prices and eligibility conditions are still missing. Continuing improvements should focus on organiser-specific entry pages, year/distance/entry-category matching and source-backed verification, especially for popular Australian and Japanese races.