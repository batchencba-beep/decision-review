---
name: decision-review
description: Turn a list of proposals (design review findings, agent suggestions, copy edits, any set of changes waiting on a human) into a one-page HTML decision board. Each card shows Today vs Proposed, with Approve / Reject / Discuss and a note; one button copies every decision back as a prompt. Use whenever you have more than two or three things for the user to decide, instead of answering with a long text list.
---

# Decision review

You hand the user a page to decide on, not a wall of text to decode. They look, click, and paste their decisions back to you.

Based on the review interface Kyle Zantos showed on Dive Club (Aug 2026): gather the proposals, let the human approve, deny or discuss each one, and copy every decision back into the session.

## When to use

- After review agents (or you) produced findings on an existing design, page or flow.
- Whenever more than two or three changes are waiting on the user's call.
- Not for a single yes/no question. Just ask that one.

## How (keep it cheap)

You never write HTML for this. You write one small JSON file and run the script. The script owns all the markup.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (the base directory shown when the skill loads). If it isn't filled in, use that folder's path.

1. If a change is visual and you can open the thing being reviewed, take the Today / Proposed images first (see "Getting the images").
2. Write `findings.json` next to where the page should live (schema below).
3. Run `python3 "${CLAUDE_SKILL_DIR}/build.py" findings.json decisions.html`. If it prints errors, fix the JSON and run it again. A warning (like a missing image) still builds, but fix it: the card will show a red "Image missing" box.
4. Check the page before showing it: `node "${CLAUDE_SKILL_DIR}/shoot.mjs" file://<abs path>/decisions.html check.png --full --width 1280`, then look at `check.png`. Every image should load and be readable. Delete `check.png` after.
5. Open it for the user (`open decisions.html` on macOS, `xdg-open` on Linux, `start` on Windows; if there's no display, just give the path) and tell them, in one line, how many decisions are waiting.
6. Stop and wait.

## Applying the decisions

The user pastes a block: the page title, a one-line instruction, then one line per card:

```
id · title → <decision in the page's language> [approve|reject|discuss|undecided] · option: … · note: …
```

The word in square brackets is always English, whatever the page language, so read that. `option` appears on choice cards, `note` only when the user wrote one. Look up each id in `findings.json` and use its `change` field (and the chosen option's `change`) for the exact edit. Then:

- **[approve]**: apply the change. On a choice card, apply the option named in the line.
- **[approve] with a note**: apply it, adjusted by the note. The note wins where they conflict.
- **[reject]**: change nothing, unless the note asks for something else ("keep it, just darken the color"). Then do what the note says, and nothing more.
- **[discuss]**: change nothing yet. Answer the note, or explain the trade-off if there's no note, and wait.
- **[undecided]**: change nothing, and list these in one line at the end so nothing is silently dropped.

Then reply with what you applied, per id, in a short list. If you rebuild the page for a second round, see "Rounds and saved decisions".

## Schema

```json
{
  "title": "Homepage review",
  "lang": "en",
  "items": [
    {
      "id": "hero-contrast",
      "title": "Hero subtitle fails contrast",
      "critical": true,
      "change": "index.html .hero p { color: #0F0F2D } (was #9A9A9A)",
      "today":    { "text": "Grey on yellow, 3.1:1.", "images": ["shots/hero-now.png"] },
      "proposed": { "text": "Ink on yellow, 12.4:1. Same size and weight.", "images": ["shots/hero-ink.png"] }
    },
    {
      "id": "card-shadow",
      "title": "Cards on grey: shadow, frame, or nothing?",
      "today": { "text": "On white, the cards blend into the background.", "images": ["shots/cards-now.png"] },
      "proposed": {
        "text": "A. On grey, the white cards already show their edge. B and C for comparison.",
        "options": [
          { "label": "A · No treatment", "recommended": true, "images": ["shots/cards-a.png"],
            "change": "styles.css .section-grey .card { box-shadow: none; border: 0 }" },
          { "label": "B · Soft shadow", "images": ["shots/cards-b.png"],
            "change": "styles.css .section-grey .card { box-shadow: 0 10px 28px -14px rgba(20,20,40,.35) }" },
          { "label": "C · Hairline", "images": [{ "src": "shots/cards-c.png", "caption": "1px at 18% ink" }],
            "change": "styles.css .section-grey .card { border: 1px solid rgba(20,20,40,.18) }" }
        ]
      }
    }
  ]
}
```

- `title` (required): names the page and starts the copied prompt. Use something specific, like "Homepage review · round 2".
- `id` (required, unique): short. It only appears in the copied prompt, never on screen.
- `change` (strongly recommended, on the item or on each option): the exact edit, never shown on the page. File, selector and values, or the exact new copy. Usually the same CSS you passed to `shoot.mjs --css`. It's what lets you, or a fresh session, apply the decision precisely.
- `today` / `proposed`: `text`, plus optionally `images` or `html` (a tiny inline-styled swatch, e.g. a color chip or a type sample).
- `images`: a path relative to the HTML file, or `{ "src", "caption", "alt", "scale" }`. A `caption` is a small label above that one image, for things like a breakpoint ("390") or a variant detail. Don't repeat the box label ("Today") in it.
- `proposed.options`: 2 to 4 variants. The user clicks one to choose it; the recommended one is pre-selected.
- `critical`: `true` only for things that are broken or blocking. Most items leave it out.
- `scale` (top level, default 2): the pixel density of your screenshots. `shoot.mjs` shoots at 2. Use 1 for ordinary 1x screenshots, or set it per image.
- `lang`: `"en"` or `"he"` (Hebrew renders right to left). `labels` overrides any button text.

## Getting the images

`shoot.mjs` (in this skill's folder) screenshots one element of a page, as it is or with your proposed CSS applied. It needs Node 22+ and Chrome, nothing to install. It works with live URLs, local dev servers and `file://` pages. Defaults: a 1440×900 viewport at 2x density.

```bash
S="${CLAUDE_SKILL_DIR}"
node $S/shoot.mjs https://example.com shots/nav-today.png --selector ".site-nav"
node $S/shoot.mjs https://example.com shots/nav-proposed.png --selector ".site-nav" --css ".site-nav{max-width:1440px}"
node $S/shoot.mjs https://example.com shots/home-mobile.png --width 390 --height 844
node $S/shoot.mjs https://example.com shots/home-full.png --full
```

- Crop to the element that changes (`--selector`), not the whole page. A full page shrunk into a card is unreadable.
- Exception: for overflow and alignment bugs, the problem is the relationship between things. Crop a common parent that contains both (e.g. the header and the hero together), or for overflow, the viewport. Avoid thin full-width strips: they become unreadable in a card.
- Render the proposal with `--css` so Today and Proposed are the same crop. The page shows every image in a card at the same scale, so a bigger element looks bigger. If the change needs markup, describe it in text instead.
- Mobile: `--width 390 --height 844`. Slow animations: raise `--wait`.
- Save images in a `shots/` folder next to the HTML and use relative paths in the JSON.
- No Node or Chrome, or nothing you can open? Use screenshots the user already has, a small `html` swatch, or a text-only card.

## Pages behind a login

If `shoot.mjs` warns that a page redirected to a sign-in page, the screens are behind a login. Don't fall back to text, and never ask for or type the user's password. Instead:

1. Tell the user, in one line, that a Chrome window will open for them to sign in, and that it uses a separate profile, not their own Chrome.
2. Run `node "${CLAUDE_SKILL_DIR}/shoot.mjs" --login <the app's address>` with a long timeout (it waits until the window is closed, up to 15 minutes).
3. The user signs in themselves, then quits that window (Cmd+Q on Mac).
4. Add `--logged-in` to every `shoot.mjs` call for that app. The session stays saved for next time.

If a `--logged-in` shot warns again, the session expired: repeat `--login`. `node "${CLAUDE_SKILL_DIR}/shoot.mjs" --logout` deletes the saved session; offer it if the user asks to sign out.

## Rounds and saved decisions

Clicks and notes are saved in the user's browser, per page. Rebuilding the same findings keeps them. A new round with different items starts clean on its own. To start over on the same findings, change the `title` (e.g. add "round 2").

## Writing the cards

The page is calm on purpose. Everything the user needs sits inside the two boxes.

- **Title**: what the decision is about, in a few words. No subtitle, no explanation under it.
- **No tags or categories** on the card besides Critical. No file names or evidence lines on screen.
- **Today**: what is there now and why it's a problem, in one or two sentences.
- **Proposed**: exactly what you'd change, with concrete values, in one or two sentences. If you recommend one option, say so and why, briefly.
- **Show, don't describe**, whenever the change is visual: a crop of the element as it is and with the change applied. If a change isn't visual (a file name, a setting), a text-only card is fine.
- One decision per card. Order: things that need a choice first, then critical, then the rest.
- Already fixed something obvious without asking? Don't put it on the page as a decision. Mention it in one line in your chat reply.
