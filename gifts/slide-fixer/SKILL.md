---
name: slide-fixer
description: Reviews an existing presentation the user already designed (an HTML or React slides artifact, or deck code) and fixes basic layout mistakes while keeping their design exactly as it is. It catches overlapping layers, text running off the slide or cut off, weak or broken proportions between title, subtitle, body and image, stretched or badly placed images, inconsistent or mixed icons, emoji used as icons, uneven margins, and titles that jump between slides. Hebrew/RTL aware. Use when the user asks to fix, clean up, tidy, polish or check their slides, or says things like "תסדר לי את המצגת", "יש חפיפות", "הפרופורציות לא נכונות", "זה נראה סלופי", "תעבור על העיצוב". Not for designing a new deck from scratch.
---

# Slide fixer

The user already has a design they like. Your job is to make it **correct**, not different. Someone who knows the deck should look at the result and say "same deck, just clean".

## Never change (their design)

- Colors, fonts, backgrounds, gradients, decorative shapes, logo, overall style.
- The layout idea of each slide (what goes where). Fix it; don't swap it for another layout.
- The wording. If text physically doesn't fit, first fix size and spacing within their scale. Shorten text or split a slide only as a last resort, and list it as a content change.
- The number and order of slides.

## What you do change

Position, size within their own scale, spacing, wrapping, layering (z-index), image fitting and cropping, icon size and style (unified to the set they already use most), RTL details. Every value you set comes from their deck: the norm, not your taste.

## Workflow

1. **Get the deck code.** If the deck is an artifact in this conversation, use its code. Otherwise ask, in one line, for the code: the HTML file, or the artifact's code copied in. Screenshots alone let you point out problems but not fix them, so say that.

2. **Measure it.** Save the code as `deck.html` (for a React artifact, wrap it in a minimal HTML page that loads React and renders it) and run:
   `python3 scripts/audit.py deck.html audit/`
   It opens the deck at 1920×1080, steps through every slide, writes a screenshot per slide to `audit/`, and prints JSON: issues per slide (with type, severity, selector and the text involved) plus `deck.norm` (the title size, title position and body size most slides use) and `deck.inconsistent` (slides that break that norm).
   - If it exits with code 2 (no Playwright or browser), try `pip install playwright && python3 -m playwright install chromium` once. If that fails, go to "No browser" below.
   - If you can view images, look at the screenshots too. The audit catches geometry; your eyes catch balance.

3. **Write down their design system** in 4 to 6 lines before touching anything: fonts, main colors, title / subtitle / body sizes in use (take `deck.norm`), side margins, image style (radius, bleed or framed, split ratio), icon set and style. This is the reference every fix converges to.

4. **Fix**, using the recipes in `references/fixes.md`. Work from `high` to `low` severity. Fix the cause in the CSS or component (one rule that fixes all slides), not by nudging single elements with magic numbers.

5. **Measure again.** Re-run the audit. Repeat until no `high` or `medium` issues are left (at most 3 rounds). Fix `low` issues only when the fix is small and clearly better. If something can't be fixed without changing their design, leave it and say so.

6. **Deliver** the fixed deck as the same kind of artifact, then a short change list in the user's language, one line per slide, in plain words:
   > שקופית 3: הכותרת חפפה לתמונה. הזזתי את התמונה לעמודה השמאלית ושמרתי על הגודל שלה.
   Then, separately: content changes (if any), and anything left as is with the reason.

## No browser

If the audit can't run, do the same review by reading the code (`references/fixes.md` lists what to look for per issue type), and offer the in-page check: add `scripts/audit.js` inside a `<script>` tag at the end of the deck, followed by
`<script>addEventListener('load',()=>setTimeout(()=>__slideAudit({overlay:true}),800))</script>`.
The deck then outlines problems in red, orange and purple on whatever slide is showing, with a "Copy report" button. Ask the user to page through, copy the report and paste it back. Remove both script tags before the final delivery.

## Hebrew / RTL checks (always)

- `dir="rtl"` on the deck root; first item of a row or sequence on the right.
- Numbers, percentages, dates, units, phone numbers and English words inside a line wrapped in `<bdi>` or `unicode-bidi:isolate`, so punctuation doesn't jump.
- Arrows that mean "next" point left. Icons with no direction (heart, check, clock) are not mirrored.
- No italics or letter-spacing on Hebrew text.

## Files

- `scripts/audit.py`: the runner (headless browser, every slide, screenshots, deck-wide norms).
- `scripts/audit.js`: the measurements, also usable inside the page as an overlay.
- `references/fixes.md`: how to fix each issue type without changing the design, with target proportions.
