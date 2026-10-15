# Race Entry Radar

A daily, conservative scanner for marathon and half-marathon websites in Australia, Japan and selected overseas destinations.

## Setup

1. Open **Settings → Pages** and choose **GitHub Actions** under Build and deployment.
2. Open **Settings → Actions → General** and enable workflow write permissions for repository contents, if not already allowed.
3. Select **Actions → Daily marathon scan and publish → Run workflow**.
4. After a successful deployment, view https://joshld.github.io/marathon-entry-scanner/.

The schedule is 21:17 UTC, equivalent to 07:17 Brisbane time. GitHub scheduled runs can be delayed.

## Important limitations

The scanner finds candidate text phrases on official websites. It **does not confirm registration availability** or determine the relevant event year, distance, residency eligibility or lottery status from a phrase alone. Some websites render content with JavaScript or block requests, and a missing signal does not mean entries are closed.

Edit `races.json` to adjust monitored races. Results are written to `data/races.json`, with changes recorded in `data/history.json`. Always verify important dates on official race pages.

## Local use

```bash
pip install -r requirements.txt
python scanner/scan.py
mkdir -p site/data
cp data/*.json site/data/
python -m http.server 8000 --directory site
```
