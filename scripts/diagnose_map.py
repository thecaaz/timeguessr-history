#!/usr/bin/env python3
"""Diagnostic script: opens the daily game, dumps the DOM near the map,
intercepts click events, and pauses so you can also inspect manually.

Run:
    python3 scripts/diagnose_map.py
"""
import asyncio
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GAME_URL = "https://timeguessr.com/roundonedaily"


async def run():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Relay console messages from the page to Python stdout
        page.on("console", lambda msg: print(f"[PAGE {msg.type.upper()}] {msg.text}"))

        # Inject event interceptor before the page loads
        await page.add_init_script("""
        window.__diag = true;
        ['pointerdown','pointerup','click','dblclick'].forEach(evt => {
            document.addEventListener(evt, (e) => {
                const el = e.target;
                console.log(`[EVENT] ${evt} on ${el.tagName}|${el.className} at (${Math.round(e.clientX)},${Math.round(e.clientY)}) bubbles=${e.bubbles}`);
            }, true);
        });
        """)

        print(f"Navigating to {GAME_URL} ...")
        await page.goto(GAME_URL, timeout=60000)

        # Click through startup dialogs
        for sel in ["a[href*='daily']", "text=Daily", "button:has-text('Daily')"]:
            el = await page.query_selector(sel)
            if el:
                print(f"Clicking daily selector: {sel}")
                await el.click()
                await page.wait_for_timeout(1000)
                break

        play_btn = await page.query_selector("#playButton > p:nth-child(1)")
        if play_btn:
            print("Clicking play button...")
            await play_btn.click()
            await page.wait_for_timeout(5000)

        cookie_sel = (
            "body > div.fc-consent-root > div.fc-dialog-container > "
            "div.fc-dialog.fc-choice-dialog > div.fc-footer-buttons-container > "
            "div.fc-footer-buttons > button.fc-button.fc-cta-consent.fc-primary-button > p"
        )
        cookie_el = await page.query_selector(cookie_sel)
        if cookie_el:
            print("Accepting cookies...")
            await cookie_el.click()
            await page.wait_for_timeout(1000)

        await page.wait_for_timeout(2000)

        # Dump DOM structure around the map
        node = await page.query_selector(".mk-map-node-element")
        if node:
            box = await node.bounding_box()
            print(f"\n=== MAP NODE BOUNDING BOX ===\n{json.dumps(box, indent=2)}")

            # Dump immediate children
            children = await page.evaluate("""
            () => {
                const n = document.querySelector('.mk-map-node-element');
                if (!n) return [];
                return Array.from(n.children).map(c => ({
                    tag: c.tagName,
                    id: c.id,
                    cls: c.className,
                    w: c.offsetWidth,
                    h: c.offsetHeight,
                }));
            }
            """)
            print(f"\n=== MAP NODE CHILDREN ===")
            for c in children:
                print(f"  {c['tag']}#{c['id']}.{c['cls']}  {c['w']}x{c['h']}")

            # Report mapkit.maps properties
            mk_info = await page.evaluate("""
            () => {
                if (!window.mapkit || !mapkit.maps || !mapkit.maps.length) return 'no mapkit.maps';
                const m = mapkit.maps[0];
                return {
                    isZoomEnabled: m.isZoomEnabled,
                    isScrollEnabled: m.isScrollEnabled,
                    isRotationEnabled: m.isRotationEnabled,
                    keys: Object.keys(m).filter(k => !k.startsWith('_')),
                };
            }
            """)
            print(f"\n=== MAPKIT MAP INFO ===\n{json.dumps(mk_info, indent=2)}")

            # Show what element is at different click positions
            if box:
                for fx, fy, label in [(0.3, 0.3, "30%/30%"), (0.5, 0.5, "50%/50%"), (0.5, 0.65, "50%/65%")]:
                    cx = box["x"] + box["width"] * fx
                    cy = box["y"] + box["height"] * fy
                    el_info = await page.evaluate(
                        "([cx,cy]) => { const e = document.elementFromPoint(cx,cy); return e ? e.tagName+'|'+e.id+'|'+e.className : 'null'; }",
                        [cx, cy]
                    )
                    print(f"  Element at {label} ({cx:.0f},{cy:.0f}): {el_info}")
        else:
            print("WARNING: .mk-map-node-element not found!")

        # Take a screenshot for reference
        shot = str(ROOT / "data" / "diagnose_map.png")
        import os; os.makedirs(str(ROOT / "data"), exist_ok=True)
        await page.screenshot(path=shot)
        print(f"\nScreenshot saved to {shot}")

        print("\n=== Now attempting a click at 50%/65% of the map ===")
        node = await page.query_selector(".mk-map-node-element")
        if node:
            box = await node.bounding_box()
            if box:
                cx = box["x"] + box["width"] * 0.5
                cy = box["y"] + box["height"] * 0.65

                # Disable MapKit zoom so click isn't swallowed
                await page.evaluate("""
                () => {
                    if (!window.mapkit || !mapkit.maps || !mapkit.maps.length) return;
                    mapkit.maps.forEach(m => {
                        try { Object.defineProperty(m, 'isZoomEnabled', { get: () => false, configurable: true }); } catch(e) {}
                    });
                    console.log('[TG] MapKit isZoomEnabled patched to false');
                }
                """)

                # Move mouse to position then wait before clicking
                await page.mouse.move(cx, cy)
                await page.wait_for_timeout(500)

                # Fire only pointerdown+pointerup+click manually to avoid extra events
                click_result = await page.evaluate("""
                ([cx, cy]) => {
                    const el = document.elementFromPoint(cx, cy);
                    if (!el) return 'no element';
                    const opts = {bubbles:true, cancelable:true, clientX:cx, clientY:cy, pointerId:1, pointerType:'mouse', isPrimary:true};
                    el.dispatchEvent(new PointerEvent('pointerdown', opts));
                    el.dispatchEvent(new PointerEvent('pointerup', opts));
                    el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, clientX:cx, clientY:cy}));
                    el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, clientX:cx, clientY:cy}));
                    el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, clientX:cx, clientY:cy}));
                    return 'dispatched on ' + el.tagName + '|' + el.className;
                }
                """, [cx, cy])
                print(f"JS dispatch result: {click_result}")
                await page.wait_for_timeout(2000)

                # Screenshot after click
                await page.screenshot(path=str(ROOT / "data" / "diagnose_after_click.png"))
                print(f"Post-click screenshot saved to data/diagnose_after_click.png")

        print("\n=== Pausing 30s so you can inspect the browser ===")
        await page.wait_for_timeout(30000)
        await browser.close()


asyncio.run(run())
