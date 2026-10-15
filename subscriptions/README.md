# Email alerts — setup and safety

**Status: disabled by default.** The repository contains the signup interface, public event detector, a secure Brevo signup Worker and an optional personalised email dispatcher. No visitor emails are accepted or sent until you configure a provider.

## Architecture

- GitHub Pages serves `site/index.html` and `site/alerts-config.json`. The configuration contains **public** URLs/site keys only; no API keys or passwords.
- `subscriptions/worker.js` runs in your Cloudflare account and collects email submissions through **Brevo's double-opt-in confirmation flow**. It verifies Cloudflare Turnstile before accepting a subscription. Email addresses and preferences are kept in Brevo, **never in this public repository**.
- Each daily GitHub scan writes verified changes to `data/alert-events.json` (no personal information).
- `notifications/dispatch.py` reads these non-personal events and fetches opted-in subscribers from Brevo. It sends a matching digest per subscriber, respecting their preferences and keeping last-send state in Brevo.

## Before activating the subscription form

1. Open a Brevo account and verify a sending address/domain using Brevo's instructions. Review the provider's current message quota. Create a contact list named `Race Entry Radar`; note the **list ID**.
2. Under Contacts > Settings > Attributes, create **TEXT** contact attributes named `RACE_PREFS` and `RACE_LAST_SENT`. The former stores the compact JSON preference object; the latter stores `YYYY-MM-DD` for duplicate suppression.
3. Create a Brevo **double-opt-in template** that uses the confirmation URL (`{{ params.DOIurl }}`). The template must explain that the recipient is confirming their Race Entry Radar registration. Note the template ID. Configure a success redirect such as `https://joshld.github.io/marathon-entry-scanner/?subscribed=1`.
4. Create a Cloudflare Turnstile widget for `joshld.github.io`. Note its **public site key** and **private secret**. You can use free-tier Cloudflare Workers and Turnstile subject to provider limits.
5. Deploy `subscriptions/worker.js` as a Cloudflare Worker (module syntax). Set these **private** Worker secrets:
   - `BREVO_API_KEY` — secret Brevo API key; needs relevant Contacts permission.
   - `TURNSTILE_SECRET` — private Turnstile secret.
   - `UNSUBSCRIBE_SECRET` — a cryptographically random string (32+ bytes). Use the **same value** in GitHub Actions.
6. Set these **non-secret** Worker environment variables:
   - `BREVO_LIST_ID`: integer contact list ID.
   - `BREVO_DOI_TEMPLATE_ID`: integer double-opt-in template ID.
   - `ALLOWED_ORIGIN`: `https://joshld.github.io` (the **origin**, not the repo path).
   - `DOI_REDIRECT_URL`: `https://joshld.github.io/marathon-entry-scanner/?subscribed=1`.
7. Test the Worker's `GET /health`. It must return `{"ready":true}` when all required settings are present. Its `POST /subscribe` endpoint accepts an email, explicit consent, preferences and a Turnstile response. Confirm that submitting a test address results in a Brevo **double-opt-in** confirmation request. Follow the confirmation link and verify that the contact appears in the right Brevo list with a `RACE_PREFS` attribute. Also test the **POST** confirmation button at `/unsubscribe`.
8. Set the following *public* values in `site/alerts-config.json` and commit them:

```json
{
  "subscription_api_url": "https://YOUR-WORKER.workers.dev",
  "turnstile_site_key": "YOUR_PUBLIC_TURNSTILE_SITE_KEY"
}
```

Only after both values are set will the form become active. **Do not put Brevo secrets in this JSON file or in GitHub Pages HTML.** Deploy this configuration before allowing real signups. Add a genuine contact address and final privacy notice for your project before going live.

## Enabling email sends

In GitHub repository Settings > Secrets and variables > Actions:

| Type | Name | Value |
|---|---|---|
| Secret | `BREVO_API_KEY` | Your Brevo API key |
| Secret | `UNSUBSCRIBE_SECRET` | Exact same secret as the Worker |
| Variable | `BREVO_LIST_ID` | Brevo list ID |
| Variable | `BREVO_SENDER_EMAIL` | Verified sender address |
| Variable | `BREVO_UNSUBSCRIBE_BASE` | Worker base URL, e.g. `https://YOUR-WORKER.workers.dev` |
| Variable | `EMAIL_ALERTS_ENABLED` | `true` **only after end-to-end testing** |

Live email dispatch runs **only on scheduled GitHub Actions runs** and requires `EMAIL_ALERTS_ENABLED=true`. Pushes and manual workflow runs don't send email; this prevents bursts from frequent development commits. Each run is capped at **100 sends** by default (`EMAIL_ALERTS_SEND_LIMIT` may lower/raise it within the script's hard 200 maximum). Review the free quota before increasing the cap.

Use `python notifications/dispatch.py` to dry-run subscriber matching locally without delivering messages. The script requires relevant env variables for list inspection. To send locally you must pass `--send`, set `EMAIL_ALERTS_ENABLED=true`, and supply all required secrets.

## Delivery and selection behaviour

- **Confirmed newly open:** Only race-status transitions into `confirmed_open` with organiser-verified `verified_entry_status=open`. Generic `possible_open` website keywords never trigger an opening email.
- **Opening soon:** Published `entry_open_date` is within 7 days and accompanied by a source. The event is deduplicated by race, alert type and entry opening date.
- **Newly added:** A race ID first appears in a nonempty watchlist. The first scan of a fresh installation does **not** mass-email the entire catalogue.
- Preferences: countries (all or selected), distances (marathon, half marathon, ultra), alert types, and **daily** or **weekly** digest.
- Weekly dispatch uses Monday in Brisbane time. Daily sends only when matching events are new. `RACE_LAST_SENT` is updated in Brevo after each accepted message.
- A one-use confirmation mechanism and provider-side list management are critical to consent. Unsubscribe uses a HMAC-signed link and a confirmation button; a mail security scanner's GET request cannot accidentally unsubscribe the user.

## Limitations and operations

- Brevo remains the source of truth for subscriber data and consent. Email service pricing/limits and account permissions may change.
- The public GitHub repository includes event data and code, **not subscriber emails**.
- This first version does not expose an interactive preference-editing page. Visitors can unsubscribe, and preference management can be added later.
- Race website scans can fail. Messages are only as accurate as manually verified race information, and places can sell out.
- Monitor delivery failures, keep the unsubscribing Worker online, and regularly test confirmation, preference matching and unsubscribe flows. Make sure the email itself identifies the operator and includes an accessible unsubscribe link.
- `GET /health` is a configuration readiness check, **not** proof of completed provider integration or real delivery.

Reference: [Brevo's official double-opt-in API](https://developers.brevo.com/reference/create-doi-contact) and [list contacts API](https://developers.brevo.com/reference/get-contacts-from-list).
