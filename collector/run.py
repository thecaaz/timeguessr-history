#!/usr/bin/env python3
"""Collector: opens timeguessr.com, reads daily round data from localStorage, saves to DB.

No game-playing required — the full dailyArray (URL, Year, Location, Description,
License, Country, StreetView, etc.) is populated in localStorage as soon as the
daily game loads.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.config import BASE_URL, DB_PATH, HEADLESS_DEFAULT
from db import dao


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Collect TimeGuessr daily challenge data")
    parser.add_argument("--date", required=False, help="Date for the game (YYYY-MM-DD). Default: today")
    parser.add_argument("--headless", dest="headless", action="store_true", help="Run browser headless")
    parser.add_argument("--headful", dest="headless", action="store_false", help="Run browser in headful mode for debugging")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB; only simulate")
    parser.set_defaults(headless=HEADLESS_DEFAULT)
    return parser.parse_args(argv)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def wait_for_daily_array(page) -> list:
    """Poll localStorage every 500 ms until dailyArray contains objects (up to ~20 s)."""
    for _ in range(40):
        result = await page.evaluate("""
        () => {
            const raw = localStorage.getItem('dailyArray');
            if (!raw) return null;
            try {
                const arr = JSON.parse(raw);
                // The site appends a sentinel 0 at the end — filter it out
                return arr.filter(e => e && typeof e === 'object');
            } catch(e) { return null; }
        }
        """)
        if result and len(result) > 0:
            return result
        await page.wait_for_timeout(500)
    return []


async def collect_for_date(date_str: str, headless: bool = HEADLESS_DEFAULT, dry_run: bool = False) -> int:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        logging.error("Playwright is not installed. Install with: pip install playwright; python3 -m playwright install")
        return 2

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        logging.info("Opening %s", BASE_URL)
        await page.goto(BASE_URL, timeout=60000)

        # Click the Daily link / button
        for sel in ["a[href*='daily']", "text=Daily", "button:has-text('Daily')"]:
            try:
                el = await page.query_selector(sel)
                if el:
                    logging.info("Clicking daily selector: %s", sel)
                    await el.click()
                    await page.wait_for_timeout(1000)
                    break
            except Exception as e:
                logging.debug("Daily selector %s failed: %s", sel, e)

        # Click the play button if it appears
        try:
            play_btn = await page.query_selector("#playButton > p:nth-child(1)")
            if play_btn:
                logging.info("Clicking play button")
                try:
                    await play_btn.click()
                except Exception:
                    await page.evaluate("el => el.click()", play_btn)
        except Exception as e:
            logging.debug("Play button not found: %s", e)

        # Wait for the page to settle and for the cookie banner to appear
        await page.wait_for_timeout(5000)

        # Accept cookie consent
        cookie_sel = (
            "body > div.fc-consent-root > div.fc-dialog-container > "
            "div.fc-dialog.fc-choice-dialog > div.fc-footer-buttons-container > "
            "div.fc-footer-buttons > button.fc-button.fc-cta-consent.fc-primary-button > p"
        )
        try:
            cookie_el = await page.query_selector(cookie_sel)
            if cookie_el:
                logging.info("Accepting cookie consent")
                try:
                    await cookie_el.click()
                except Exception:
                    await page.evaluate("el => el.click()", cookie_el)
                await page.wait_for_timeout(500)
        except Exception as e:
            logging.debug("Cookie consent not found: %s", e)

        # Read dailyArray — the site populates this before the first round renders
        logging.info("Waiting for dailyArray in localStorage...")
        daily_array = await wait_for_daily_array(page)

        if not daily_array:
            logging.error("dailyArray not found in localStorage after waiting. Aborting.")
            await browser.close()
            return 1

        logging.info("Got %d rounds from dailyArray", len(daily_array))
        for i, entry in enumerate(daily_array):
            logging.info(
                "  Round %d: Year=%s Country=%s URL=%.60s",
                i + 1, entry.get("Year"), entry.get("Country"), entry.get("URL") or "",
            )

        if dry_run:
            logging.info("--dry-run: skipping DB write")
            await browser.close()
            return 0

        conn = dao.init_db(DB_PATH)
        daily_id = daily_array[0].get("DailyId") if daily_array else None
        game_id = dao.insert_game(conn, date_str, daily_id=daily_id)

        for seq, entry in enumerate(daily_array, start=1):
            loc = entry.get("Location") or {}
            raw_year = entry.get("Year")
            try:
                year = int(raw_year) if raw_year else None
            except (ValueError, TypeError):
                year = None

            dao.insert_screenshot(
                conn,
                game_id=game_id,
                seq=seq,
                image_url=entry.get("URL"),
                location_text=entry.get("Country"),
                lat=loc.get("lat"),
                lng=loc.get("lng"),
                year=year,
                description=entry.get("Description"),
                image_id=entry.get("ImageId"),
                street_view=entry.get("StreetView") or None,
                license=entry.get("License"),
                country=entry.get("Country"),
            )
            logging.info("Saved round %d", seq)

        conn.close()
        await browser.close()

    logging.info("Collection complete for %s", date_str)
    return 0


def main():
    args = parse_args()
    date_str = args.date or datetime.utcnow().date().isoformat()
    res = asyncio.run(collect_for_date(date_str, headless=args.headless, dry_run=args.dry_run))
    raise SystemExit(res)


if __name__ == "__main__":
    main()

