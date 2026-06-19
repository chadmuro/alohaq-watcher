# AlohaQ Renewal Watcher

Checks Honolulu AlohaQ for **driver-license renewal** openings at your chosen
locations and dates, and **emails your Gmail** when a slot opens.

Locations and dates are configured in `check.py` (`LOCATION_CODES` and
`TARGET_DATES`).

## Setup

1. **Gmail App Password**: turn on 2-Step Verification, then create an App
   Password at https://myaccount.google.com/apppasswords.
2. **Push this repo to GitHub.**
3. **Add repo secrets** (Settings → Secrets and variables → Actions):
   - `GMAIL_USER` — your gmail address
   - `GMAIL_APP_PASS` — the 16-char app password
   - `NOTIFY_TO` — where to send alerts
4. **Enable Actions write permission**: Settings → Actions → General →
   Workflow permissions → Read and write permissions.
5. **Set up an external cron job** (e.g. cron-job.org) to POST to your repo's
   GitHub Actions workflow dispatch API every 15 minutes, with a scoped
   GitHub access token for auth.
6. **Trigger a manual run** to confirm: repo → Actions → alohaq-watcher → Run
   workflow.
