# AlohaQ Renewal Watcher

Checks Honolulu AlohaQ for **driver-license renewal** openings at 5 locations on
your target dates, and **emails your Gmail** when a slot opens. Runs free, 24/7
on GitHub Actions every 15 minutes.

Locations watched: Kapalama Driver License, Downtown / Hawaii Kai / Pearlridge /
Windward City Satellite City Halls.
Dates watched: 6/24, 6/25, 6/26, 7/1, 7/2, 7/3, 7/6.

---

## Setup (one time, ~15 min)

### 1. Make a Gmail App Password
1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Create an App Password: https://myaccount.google.com/apppasswords
   → pick "Mail" / "Other", name it `alohaq`. Copy the 16-char code.

### 2. Put this folder in a GitHub repo
- Create a new **private** repo on GitHub.
- Upload these files (or `git push` them).

### 3. Add repo secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name             | Value                                  |
|------------------|----------------------------------------|
| `GMAIL_USER`     | your gmail address                     |
| `GMAIL_APP_PASS` | the 16-char app password (no spaces)   |
| `NOTIFY_TO`      | where to send alerts (your gmail)      |

### 4. Enable Actions write permission
Repo → **Settings → Actions → General → Workflow permissions** →
select **Read and write permissions** → Save.
(Needed so it can save `seen.json` and not re-alert you every 15 min.)

### 5. Confirm the selectors  ⚠️ THE ONE MANUAL STEP
The site is a JS booking app and blocks bots from outside, so the CSS
selectors in `check.py` are best-guess placeholders. Finalize them once:

```bash
pip install playwright
playwright install chromium
HEADLESS=0 python check.py        # watch the real browser drive the site
```

Watch where it stalls. In the four functions marked `>>> CONFIRM SELECTOR <<<`
(`pick_location`, `pick_service`, `read_open_dates`, and the "next month" arrow),
right-click the real element in your browser → Inspect → adjust the selector to
match. Re-run until `[checked] <location>: N open target date(s)` prints sensibly
(test it against a date you KNOW is open to confirm detection works).

### 6. Go live
Commit your selector fixes. The workflow already runs every 15 min. Trigger a
first run manually: repo → **Actions → alohaq-watcher → Run workflow**.

---

## Notes & tuning
- **Frequency:** edit the `cron` in `.github/workflows/watcher.yml`. `*/15` =
  every 15 min. Don't go below ~10 min — be polite to a government site and
  avoid looking like an attack.
- **No double-spam:** `seen.json` records each `(location, date)` already
  alerted. You get re-alerted only if a slot disappears and later reappears.
- **Watch hour:** slots are released daily ~4:15 p.m. Hawaii time (cancellations
  appear all day). 4:15 p.m. HST = 02:15 UTC next day — the */15 schedule covers it.
- **Booking is still manual.** This only *notifies*; it does not auto-book
  (booking needs your identity + SMS verification). When you get the email, open
  the link and grab it fast — these go quickly.
- **Debugging in CI:** the Actions run log shows each location's result. If a run
  errors, check that log first.

## Legal/etiquette
You're polling a public government booking page at a modest rate to watch for
your own appointment. Keep the interval reasonable (≥10 min), don't parallelize
aggressively, and don't auto-book. That keeps this firmly in "personal
availability alert" territory.
