#!/usr/bin/env python3
"""Audit a slide deck in a headless browser.

usage: python3 audit.py deck.html [out_dir]

Opens the deck at 1920x1080, finds the slides (all at once, or one at a time
by pressing next), runs audit.js on each, takes a screenshot of each slide,
and prints a JSON report with per-slide issues plus deck-wide consistency
(title size and position, body size, margins, image share, icon styles).
Needs Playwright with Chromium. If it is missing, the script says so and
exits with code 2, so the caller can fall back to the in-page overlay.
"""
import json, os, statistics, sys, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    deck = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(deck), 'audit'))
    os.makedirs(out, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"error": "playwright not installed", "fallback": "use the in-page overlay (see SKILL.md)"})); sys.exit(2)
    js = open(os.path.join(HERE, 'audit.js'), encoding='utf-8').read()

    with sync_playwright() as p:
        b, err = None, ""
        import shutil
        paths = [None, os.environ.get("CHROME_PATH"), "/opt/pw-browsers/chromium", shutil.which("chromium"),
                 shutil.which("chromium-browser"), shutil.which("google-chrome")]
        for path in paths:
            if path is None and b is None and paths.index(path) > 0: continue
            try:
                b = p.chromium.launch(executable_path=path, args=["--no-sandbox"]) if path else p.chromium.launch()
                break
            except Exception as e:
                err = str(e)[:200]
        if b is None:
            print(json.dumps({"error": "no browser: " + err, "fallback": "use the in-page overlay"})); sys.exit(2)
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)[:200]))
        pg.goto("file://" + deck); pg.wait_for_timeout(1500)
        pg.add_script_tag(content=js)

        def run():
            return pg.evaluate("window.__slideAudit()")

        slides, seen = [], set()
        first = run()
        if len(first["slides"]) > 1:            # all slides on the page at once (scroll or grid)
            slides = first["slides"]
            pg.screenshot(path=os.path.join(out, "all.png"), full_page=True)
        else:                                    # one slide at a time: step through
            keys = None
            for n in range(80):
                sig = hashlib.md5(pg.screenshot()).hexdigest()
                if sig in seen: break
                seen.add(sig)
                r = run()["slides"][0]; r["slide"] = n + 1
                slides.append(r)
                pg.screenshot(path=os.path.join(out, "slide-%02d.png" % (n + 1)))
                moved = False
                for k in ([keys] if keys else ["ArrowRight", "ArrowLeft", "PageDown", "Space"]):
                    pg.keyboard.press(k); pg.wait_for_timeout(450)
                    if hashlib.md5(pg.screenshot()).hexdigest() not in seen:
                        keys, moved = k, True; break
                if not moved: break
        b.close()

    print(json.dumps({"slides": slides, "deck": consistency(slides), "page_errors": errors, "screenshots": out}, ensure_ascii=False, indent=1))

def consistency(slides):
    """Find the deck's own norm and list slides that break it."""
    infos = [s["info"] for s in slides if s["info"].get("titleSize")]
    rep = {"slides": len(slides)}
    if len(infos) < 3:
        return rep
    def mode(vals):
        vals = [v for v in vals if v is not None]
        return statistics.mode(vals) if vals else None
    # content slides = skip the largest-title slides (cover, section dividers)
    ts = sorted(i["titleSize"] for i in infos)
    content = [s for s in slides if s["info"].get("titleSize")]
    norm = {
        "titleSize": mode([s["info"]["titleSize"] for s in content if s["info"]["titleSize"] <= ts[int(len(ts) * 0.6)]]),
        "titleTop": None,
    }
    T = norm["titleSize"]
    same = [s for s in content if T and abs(s["info"]["titleSize"] - T) / T <= 0.1]
    norm["titleTop"] = mode([round(s["info"]["titleTop"] / 8) * 8 for s in same])
    norm["bodySize"] = mode([s["info"].get("bodySize") for s in same])
    rep["norm"] = norm
    off = []
    for s in content:
        i = s["info"]
        T = norm["titleSize"]
        if not T: break
        d = (i["titleSize"] - T) / T
        # much bigger titles are deliberate special slides (cover, section, closing): skip them
        if d > 0.3: continue
        if abs(d) > 0.1:
            off.append({"slide": s["slide"], "type": "title-size-inconsistent", "severity": "medium", "message": "Title is %dpx; most slides use %dpx" % (i["titleSize"], T)})
            continue
        # a title centered low on the slide is a deliberate hero layout (cover, closing)
        if norm["titleTop"] is not None and i["titleTop"] < 0.3 * i.get("slideWidth", 1920) * 9 / 16 and abs(i["titleTop"] - norm["titleTop"]) > 24:
            off.append({"slide": s["slide"], "type": "title-position-inconsistent", "severity": "medium", "message": "Title starts at y=%d; most slides at y=%d" % (i["titleTop"], norm["titleTop"])})
        B = norm["bodySize"]
        if B and i.get("bodySize") and i["bodySize"] != i["titleSize"] and abs(i["bodySize"] - B) / B > 0.15:
            off.append({"slide": s["slide"], "type": "body-size-inconsistent", "severity": "low", "message": "Body text is %dpx; most slides use %dpx" % (i["bodySize"], B)})
    styles = set(st for s in slides for st in s["info"].get("iconStyles", []))
    if len(styles) > 1:
        off.append({"slide": None, "type": "icon-styles-deck", "message": "Deck mixes icon styles: " + ", ".join(sorted(styles))})
    rep["inconsistent"] = off
    rep["issue_count"] = sum(len(s["issues"]) for s in slides) + len(off)
    return rep

if __name__ == "__main__":
    main()
