#!/usr/bin/env python3
"""
AlohaQ driver-license-renewal appointment watcher.

Checks a set of Honolulu satellite/driver-licensing locations for open
renewal appointment slots on a set of target dates, and emails you (Gmail)
when something opens up. De-duplicates so you only get alerted once per
(location, date) until it disappears and reappears.

CONFIG comes from environment variables (set as GitHub Actions secrets):
  GMAIL_USER       your gmail address, e.g. you@gmail.com
  GMAIL_APP_PASS   16-char Gmail App Password (NOT your normal password)
  NOTIFY_TO        where to send the alert (usually same as GMAIL_USER)

Run locally first to debug:  HEADLESS=0 python check.py
"""

import os
import sys
import json
import smtplib
import datetime as dt
from email.mime.text import MIMEText
from pathlib import Path

from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

START_URL = (
    "https://alohaq.honolulu.gov/?1&cat=1"
    "&name=Driver%20Licensing%20and%20Satellite%20Services"
)

# Locations to check, mapped to their data-loc-val codes on the site.
LOCATION_CODES = {
    "Kapalama Driver License": "KAPA",
    "Downtown Satellite City Hall": "FSCH",
    "Hawaii Kai Satellite City Hall": "HKAI",
    "Pearlridge Satellite City Hall": "PEAR",
    "Windward City Satellite City Hall": "WIND",
}

LOCATIONS = list(LOCATION_CODES.keys())

# The renewal service's data-trans-name varies by location. Confirmed names:
SERVICE_NAMES = [
    "Hawaii License Renewal",                  # Kapalama
    "DRIVER LICENSE & STATE ID Renewals",      # Downtown, and likely other satellite city halls
]

# Fallback keyword match on visible text if none of SERVICE_NAMES match.
SERVICE_KEYWORDS = ["renew", "renewal", "driver license", "drivers license"]

# Target dates we care about (year is current year unless month already passed).
TARGET_DATES = [
    (6, 24), (6, 25), (6, 26),
    (7, 1), (7, 2), (7, 3),
    (7, 6),
    (10, 1),  # TEMP: testing only, likely-open date to verify the email flow
]

# File that remembers what we've already alerted on (committed back by CI).
STATE_FILE = Path("seen.json")

HEADLESS = os.environ.get("HEADLESS", "1") != "0"
NAV_TIMEOUT = 30_000  # ms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def target_dates_resolved():
    """Return target dates as datetime.date for the right year."""
    today = dt.date.today()
    out = []
    for mo, day in TARGET_DATES:
        year = today.year
        # If the month is already well in the past, assume next year.
        if mo < today.month - 1:
            year += 1
        out.append(dt.date(year, mo, day))
    return out


def load_seen():
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    STATE_FILE.write_text(json.dumps(sorted(seen), indent=2))


def send_email(subject, body):
    user = os.environ["GMAIL_USER"]
    app_pass = os.environ["GMAIL_APP_PASS"]
    to = os.environ.get("NOTIFY_TO", user)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, app_pass)
        s.sendmail(user, [to], msg.as_string())
    print(f"[email] sent to {to}: {subject}")


# ---------------------------------------------------------------------------
# Site interaction
#
# NOTE: AlohaQ is a Qmatic-style queue/booking app. The exact CSS selectors
# below are PLACEHOLDERS based on the typical structure. You must confirm them
# against the live page (DevTools) and tweak the four functions marked
# >>> CONFIRM SELECTOR <<<. Everything else is generic.
# ---------------------------------------------------------------------------

def open_start(page):
    page.goto(START_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
    # The location tiles render client-side after some JS/AJAX delay, so wait
    # for at least one to actually show up instead of a fixed sleep.
    try:
        page.wait_for_selector("div.location", timeout=NAV_TIMEOUT)
    except Exception:
        pass


def pick_location(page, location_name):
    """Click into a location tile, matched by its data-loc-val code."""
    code = LOCATION_CODES.get(location_name)
    if not code:
        return False
    tile = page.locator(f"div.location[data-loc-val='{code}']")
    if tile.count() == 0:
        return False
    tile.first.scroll_into_view_if_needed()
    tile.first.click()
    page.wait_for_timeout(2500)
    return True


def pick_service(page):
    """Choose the renewal service (transaction tile) inside a location."""
    try:
        page.wait_for_selector("div.transaction", timeout=NAV_TIMEOUT)
    except Exception:
        pass
    tile = None
    for name in SERVICE_NAMES:
        candidate = page.locator(f"div.transaction[data-trans-name='{name}']")
        if candidate.count() > 0:
            tile = candidate
            break
    if tile is None:
        tile = page.locator("div.transaction[data-trans-name*='renew' i]")
    if tile.count() == 0:
        # Fall back to keyword match on visible text.
        for kw in SERVICE_KEYWORDS:
            loc = page.get_by_text(kw, exact=False)
            if loc.count() > 0:
                loc.first.click()
                page.wait_for_timeout(2500)
                return True
        return False
    tile.first.scroll_into_view_if_needed()
    tile.first.click()
    page.wait_for_timeout(2500)
    return True


def confirm_required_docs(page):
    """Click through the 'I have ALL the Required Documents' confirmation."""
    btn = page.locator("#requiredDoc")
    if btn.count() == 0:
        return False
    btn.first.scroll_into_view_if_needed()
    btn.first.click()
    page.wait_for_timeout(2500)
    return True


def _displayed_month_year(page):
    """Read the (year, month) currently shown by the jQuery UI datepicker."""
    month_name = page.locator(".ui-datepicker-month").first.text_content().strip()
    year_text = page.locator(".ui-datepicker-year").first.text_content().strip()
    month_num = dt.datetime.strptime(month_name, "%B").month
    return int(year_text), month_num


def _click_calendar_arrow(page, direction):
    """Click the prev/next arrow. Returns False if missing or disabled
    (disabled means there's nothing further in that direction)."""
    sel = "a.ui-datepicker-prev" if direction == "prev" else "a.ui-datepicker-next"
    arrow = page.locator(sel)
    if arrow.count() == 0:
        return False
    cls = arrow.first.get_attribute("class") or ""
    if "ui-state-disabled" in cls:
        return False
    arrow.first.click()
    page.wait_for_timeout(800)
    return True


def _navigate_to_month(page, target_year, target_month, max_steps=24):
    """Page the calendar to (target_year, target_month).
    Returns False if blocked before reaching it (no appointments that far
    in the requested direction)."""
    for _ in range(max_steps):
        cur_year, cur_month = _displayed_month_year(page)
        if (cur_year, cur_month) == (target_year, target_month):
            return True
        direction = "prev" if (target_year, target_month) < (cur_year, cur_month) else "next"
        if not _click_calendar_arrow(page, direction):
            return False
    return False


def read_open_dates(page, wanted_dates):
    """Return the subset of wanted_dates that have an open appointment slot.

    The site uses a jQuery UI datepicker (#datepicker). Available days render
    as <a aria-label="Month D, YYYY"> inside the <td>; unavailable days render
    as a plain <span> with no link. So presence of that <a> is a clean
    available/unavailable signal, no class-name guessing needed.
    """
    found = []
    try:
        page.wait_for_selector("#datepicker", timeout=NAV_TIMEOUT)
    except Exception:
        return found

    for d in sorted(wanted_dates):
        if not _navigate_to_month(page, d.year, d.month):
            continue  # calendar can't reach that month -> no slots there
        aria_label = f"{d.strftime('%B')} {d.day}, {d.year}"
        cell = page.locator(f"#datepicker a[aria-label='{aria_label}']")
        if cell.count() > 0:
            found.append(d)
    return found


def check_location(page, location_name, wanted_dates):
    """Full flow for one location; returns list of open target dates."""
    open_start(page)
    if not pick_location(page, location_name):
        print(f"[warn] could not find location: {location_name}")
        return []
    if not pick_service(page):
        print(f"[warn] could not find service for: {location_name}")
        return []
    confirm_required_docs(page)
    opens = read_open_dates(page, wanted_dates)
    return opens


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    wanted = target_dates_resolved()
    print(f"[info] target dates: {[d.isoformat() for d in wanted]}")

    seen = load_seen()
    new_hits = []          # (location, date) tuples to alert on
    current_hits = set()   # everything open right now (to prune stale 'seen')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0 Safari/537.36"),
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        page.set_default_timeout(NAV_TIMEOUT)

        for loc in LOCATIONS:
            try:
                opens = check_location(page, loc, wanted)
            except Exception as e:
                print(f"[error] {loc}: {e}")
                opens = []
            for d in opens:
                key = f"{loc} | {d.isoformat()}"
                current_hits.add(key)
                if key not in seen:
                    new_hits.append((loc, d))
            print(f"[checked] {loc}: {len(opens)} open target date(s)")

        browser.close()

    # Prune seen entries that are no longer open, so a slot that reappears
    # later will alert again.
    seen = (seen & current_hits) | {f"{l} | {d.isoformat()}" for l, d in new_hits}

    if new_hits:
        lines = [f"  • {l} — {d.strftime('%a %b %d, %Y')}" for l, d in new_hits]
        body = (
            "Driver-license renewal openings found on AlohaQ:\n\n"
            + "\n".join(lines)
            + f"\n\nBook now: {START_URL}\n\n"
            "(You're getting this once per slot until it disappears.)"
        )
        try:
            send_email(
                subject=f"🚗 AlohaQ: {len(new_hits)} renewal slot(s) open",
                body=body,
            )
        except Exception as e:
            print(f"[error] email failed: {e}")
            # Don't lose the alert: don't persist as 'seen' if email failed.
            seen -= {f"{l} | {d.isoformat()}" for l, d in new_hits}
            save_seen(seen)
            sys.exit(1)
    else:
        print("[info] no new openings.")

    save_seen(seen)


if __name__ == "__main__":
    main()
