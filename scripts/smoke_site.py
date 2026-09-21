#!/usr/bin/env python3
"""Load the built site in a headless browser and fail on what a reader would hit.

Three contracts, checked on every page under site/:

  1. No horizontal overflow at a 390px phone width. A generated decision page
     once measured 429px wide because of a five-column table.
  2. No serious or critical axe-core violation, colour contrast included. An
     outside review counted 57 low-contrast elements on the homepage.
  3. On the homepage, opening a row puts focus inside the dialog, Tab stays
     inside it, and Escape returns focus to the row that opened it.

    pip install playwright && playwright install chromium
    python3 scripts/smoke_site.py

Serves site/ on a local port; no network beyond fetching axe-core from cdnjs.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
PHONE = {"width": 390, "height": 844}
SEVERE = {"serious", "critical"}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D102 - silence per-request lines
        pass


def serve() -> tuple[socketserver.TCPServer, int]:
    handler = partial(Quiet, directory=str(SITE))
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def pages() -> list[str]:
    out = ["index.html", "terms.html", "privacy.html", "404.html"]
    out += sorted(f"decision/{p.name}" for p in (SITE / "decision").glob("*.html"))
    return [p for p in out if (SITE / p).exists()]


def main() -> None:
    srv, port = serve()
    base = f"http://127.0.0.1:{port}/"
    failures: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for scheme in ("light", "dark"):
            ctx = browser.new_context(viewport=PHONE, color_scheme=scheme)
            page = ctx.new_page()
            for rel in pages():
                page.goto(base + rel, wait_until="networkidle")
                page.wait_for_timeout(300)
                width = page.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)")
                if width > PHONE["width"]:
                    failures.append(f"{scheme} {rel}: page is {width}px wide at {PHONE['width']}px")
                page.add_script_tag(url=AXE_URL)
                result = page.evaluate("axe.run(document, {resultTypes: ['violations']})")
                for v in result["violations"]:
                    if v["impact"] in SEVERE:
                        nodes = len(v["nodes"])
                        sample = v["nodes"][0]["target"][0] if v["nodes"] else ""
                        failures.append(f"{scheme} {rel}: axe {v['id']} ({v['impact']}) on {nodes} element(s), e.g. {sample}")
                print(f"{scheme:5} {rel:40} {width}px  axe severe: "
                      f"{sum(1 for v in result['violations'] if v['impact'] in SEVERE)}")
            ctx.close()

        # dialog focus contract, desktop width so the row buttons are the ones laid out
        ctx = browser.new_context(viewport={"width": 1200, "height": 900})
        page = ctx.new_page()
        page.goto(base + "index.html", wait_until="networkidle")
        page.wait_for_timeout(300)
        first = page.locator("[data-task]:visible").first
        task = first.get_attribute("data-task")
        first.focus()
        first.click()
        page.wait_for_timeout(200)
        state = page.evaluate("""() => {
            const d = document.querySelector('[role="dialog"]');
            return { open: !!d, inside: !!d && d.contains(document.activeElement) };
        }""")
        if not (state["open"] and state["inside"]):
            failures.append(f"dialog: after opening {task}, focus is not inside the dialog ({state})")
        for _ in range(40):
            page.keyboard.press("Tab")
        inside = page.evaluate("""() => {
            const d = document.querySelector('[role="dialog"]');
            return !!d && d.contains(document.activeElement);
        }""")
        if not inside:
            failures.append("dialog: focus escaped the dialog after 40 Tab presses")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        back = page.evaluate("document.activeElement && document.activeElement.getAttribute('data-task')")
        if back != task:
            failures.append(f"dialog: Escape returned focus to {back!r}, expected the {task!r} row")
        print(f"dialog focus contract on {task}: {'ok' if not any(f.startswith('dialog') for f in failures) else 'FAILED'}")
        ctx.close()
        browser.close()
    srv.shutdown()

    if failures:
        print()
        for f in failures:
            print("FAIL", f)
        raise SystemExit(f"\n{len(failures)} smoke check(s) failed")
    print(f"\nSMOKE PASSED: {len(pages())} pages in light and dark at {PHONE['width']}px, no severe axe violation, dialog keeps focus")


if __name__ == "__main__":
    main()
