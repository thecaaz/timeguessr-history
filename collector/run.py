#!/usr/bin/env python3
"""Collector stub that opens timeguessr and attempts to collect round image URLs and metadata.

This is a best-effort prototype: selectors and interactions will likely need tuning
against the live site. The script gracefully exits if Playwright is not installed.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

# When executed directly (python3 collector/run.py) the package imports may fail
# because the repository root isn't on sys.path. Ensure the repo root is present
# so `from collector.config` and `from db import dao` work when run as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.config import BASE_URL, ROUNDS, DB_PATH, HEADLESS_DEFAULT
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


async def collect_for_date(date_str: str, headless: bool = HEADLESS_DEFAULT, dry_run: bool = False) -> int:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        logging.error("Playwright is not installed. Install with: pip install playwright; python -m playwright install")
        return 2

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        logging.info("Opening %s", BASE_URL)
        await page.goto(BASE_URL, timeout=60000)

        # Best-effort: try to click a daily link/button if present
        for sel in ["a[href*='daily']", "text=Daily", "button:has-text('Daily')"]:
            try:
                el = await page.query_selector(sel)
                if el:
                    logging.info("Found daily selector: %s", sel)
                    await el.click()
                    await page.wait_for_timeout(1000)
                    break
            except Exception as e:
                logging.debug("Error checking daily selector %s: %s", sel, e, exc_info=True)
                continue

        # Some flows show an extra play button after the daily dialog appears.
        # Click it if present (selector provided by user).
        try:
            play_btn = await page.query_selector("#playButton > p:nth-child(1)")
            if play_btn:
                logging.info("Found #playButton play element, clicking it")
                try:
                    await play_btn.click()
                except Exception as e:
                    logging.debug("play_btn.click() failed, trying JS click: %s", e, exc_info=True)
                    # Some elements may require scrolling into view or JS click
                    await page.evaluate("el => el.click()", play_btn)
                # Wait a bit for subsequent UI (cookie popup) to appear
                await page.wait_for_timeout(5000)

                # Accept cookie consent if dialog appears (some flows show it after play).
                try:
                    cookie_sel = (
                        "body > div.fc-consent-root > div.fc-dialog-container > "
                        "div.fc-dialog.fc-choice-dialog > div.fc-footer-buttons-container > "
                        "div.fc-footer-buttons > button.fc-button.fc-cta-consent.fc-primary-button > p"
                    )
                    cookie_el = await page.query_selector(cookie_sel)
                    if cookie_el:
                        logging.info("Found cookie-accept element, clicking it")
                        try:
                            await cookie_el.click()
                        except Exception as e:
                            logging.debug("cookie_el.click() failed, trying JS click: %s", e, exc_info=True)
                            await page.evaluate("el => el.click()", cookie_el)
                        await page.wait_for_timeout(500)
                except Exception as e:
                    logging.debug("Cookie accept check failed: %s", e, exc_info=True)
        except Exception:
            logging.debug("Play button flow failed", exc_info=True)

        rounds = []
        for seq in range(1, ROUNDS + 1):
            logging.info("Collecting round %d", seq)
            # Wait a short while for content to settle
            await page.wait_for_timeout(1000)

            image_url = None
            try:
                img = await page.query_selector("img")
                if img:
                    src = await img.get_attribute("src")
                    if src:
                        if src.startswith("//"):
                            src = "https:" + src
                        image_url = src
            except Exception as e:
                logging.debug("Failed to read image src for seq %d: %s", seq, e, exc_info=True)
                image_url = None

            logging.info("Round %d image URL: %s", seq, image_url)

            # After the image and map are shown, select a location on the map.
            # Wait for the map canvas to be interactive before touching it.
            await page.wait_for_timeout(1500)
            try:
                node = await page.query_selector(".mk-map-node-element")
                if node:
                    logging.info("Found map node element at seq %d", seq)
                    box = await node.bounding_box()
                    if not box:
                        logging.warning("No bounding box for map node at seq %d", seq)
                    else:
                        # Click at 50% x, 65% y: center horizontally, slightly below center
                        # vertically to avoid MapKit's compass (top-right) and
                        # zoom controls (top/bottom right corners).
                        cx = box["x"] + box["width"] * 0.5
                        cy = box["y"] + box["height"] * 0.65

                        diag = await page.evaluate(
                            "([cx, cy]) => { const el = document.elementFromPoint(cx, cy); "
                            "return el ? el.tagName + '|' + el.id + '|' + el.className : 'null'; }",
                            [cx, cy]
                        )
                        logging.info("Map click target element: %s at (%.0f, %.0f)", diag, cx, cy)

                        # Disable MapKit's built-in scroll/zoom gestures so our click
                        # is not consumed and zoomed by MapKit before reaching the game layer.
                        try:
                            await page.evaluate("""
                            () => {
                                if (!window.mapkit || !mapkit.maps || !mapkit.maps.length) return;
                                mapkit.maps.forEach(m => {
                                    try {
                                        Object.defineProperty(m, 'isZoomEnabled',   { get: () => false, configurable: true });
                                        Object.defineProperty(m, 'isScrollEnabled', { get: () => false, configurable: true });
                                    } catch(e) {}
                                });
                            }
                            """)
                            logging.debug("MapKit zoom/scroll disabled")
                        except Exception as e:
                            logging.debug("MapKit disable failed: %s", e)

                        # Move the real mouse cursor to the target so MapKit's pointer
                        # tracking is at our click position before we fire events.
                        await page.mouse.move(cx, cy)
                        await page.wait_for_timeout(300)

                        # Dispatch the full pointer+mouse+click event sequence directly
                        # via JavaScript.  This bypasses Playwright's internal mouse.click()
                        # which calls mouse.move() again (extra pointermove) and applies a
                        # delay between down/up that MapKit can misinterpret as a long-press.
                        click_result = await page.evaluate("""
                        ([cx, cy]) => {
                            const el = document.elementFromPoint(cx, cy);
                            if (!el) return 'no element at point';
                            const po = { bubbles: true, cancelable: true, clientX: cx, clientY: cy,
                                         pointerId: 1, pointerType: 'mouse', isPrimary: true };
                            const mo = { bubbles: true, cancelable: true, clientX: cx, clientY: cy };
                            el.dispatchEvent(new PointerEvent('pointerover',  po));
                            el.dispatchEvent(new PointerEvent('pointerenter', po));
                            el.dispatchEvent(new PointerEvent('pointerdown',  po));
                            el.dispatchEvent(new MouseEvent('mousedown', mo));
                            el.dispatchEvent(new PointerEvent('pointerup',    po));
                            el.dispatchEvent(new MouseEvent('mouseup',   mo));
                            el.dispatchEvent(new MouseEvent('click',     mo));
                            return 'ok:' + el.tagName + '|' + el.id + '|' + el.className;
                        }
                        """, [cx, cy])
                        logging.info("Map JS dispatch result: %s", click_result)
                        await page.wait_for_timeout(500)
                else:
                    logging.warning("Map node element not found at seq %d", seq)
            except Exception as e:
                logging.exception("Map interaction failed at seq %d", seq)

            # Click the make guess button to submit the guess
            try:
                make_btn = await page.query_selector("#makeGuess")
                if make_btn:
                    logging.info("Clicking #makeGuess button")
                    try:
                        await make_btn.click()
                    except Exception:
                        await page.evaluate("el => el.click()", make_btn)
                else:
                    # fallback: common text label
                    make_btn2 = await page.query_selector("button:has-text('Make guess')")
                    if make_btn2:
                        await make_btn2.click()
            except Exception:
                logging.exception("Failed to click make guess button")

            # Wait briefly for the round reveal to show
            await page.wait_for_timeout(1500)

            # Attempt to advance the game to next round
            advanced = False
            for next_sel in ["button:has-text('Next')", "button:has-text('Continue')", "text=Next"]:
                try:
                    n = await page.query_selector(next_sel)
                    if n:
                        await n.click()
                        advanced = True
                        break
                except Exception as e:
                    logging.debug("Error advancing with selector %s: %s", next_sel, e, exc_info=True)
                    continue

            if not advanced:
                # try keyboard navigation as a fallback
                try:
                    await page.keyboard.press("ArrowRight")
                except Exception as e:
                    logging.debug("Keyboard navigation failed: %s", e, exc_info=True)

            rounds.append({
                "seq": seq,
                "image_url": image_url,
                "location_text": None,
                "lat": None,
                "lng": None,
                "year": None,
                "description": None,
            })

            await page.wait_for_timeout(500)

        # Save results to DB
        conn = dao.init_db(DB_PATH)
        game_id = dao.insert_game(conn, date_str)
        for r in rounds:
            dao.insert_screenshot(
                conn,
                game_id,
                r["seq"],
                r["image_url"],
                r["location_text"],
                r["lat"],
                r["lng"],
                r["year"],
                r["description"],
            )
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
