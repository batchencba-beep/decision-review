---
name: live-edit
description: Open a screen in Chrome with a Figma-style editor on top (layers, a design panel, drag, resize, inline text editing) so the user can design it by hand, then read back every change as structured data (edits.json) and build it into the source, including any interactions they described. Use when the user wants to tweak, adjust, nudge or restyle something themselves ("let me edit it", "I want to move this by hand", "open it in edit mode", "אני רוצה לערוך ידנית", "תן לי לשחק עם זה"), and offer it after you build a page or HTML artifact whose visual details the user will want to fine-tune. Works on local HTML files and live URLs.
---

# Live edit

Some things are faster to do than to describe. The user edits the screen the way they would in Figma, clicks **Send to Claude**, and you get an exact list of what changed: element, property, before, after. Then you build those changes into the real code, along with any behavior they wrote down.

## When to use

- The user wants to adjust a screen by hand: spacing, type, color, size, order, copy, card style.
- Right after you build a page or an HTML artifact, if the user is likely to fine-tune it. Offer it in one line ("Want to adjust it by hand? I'll open it in the editor."), don't open it uninvited.
- Not for a change the user already described exactly. Just make it.

## Open the editor

`${CLAUDE_SKILL_DIR}` is this skill's folder. If it isn't filled in, use that folder's path.

```bash
node "${CLAUDE_SKILL_DIR}/edit.mjs" <file.html | url> --out <dir>/edits.json --lang he
```

- Pass the **local HTML file** for anything you built. For a claude.ai artifact, edit the file you published it from. If you only have the link, read it with the Artifact tool, save the page to a file, and open that.
- `--lang he` or `--lang en`: the language the user writes to you in.
- `--width 390 --height 844` to edit the mobile layout.
- `--logged-in` for pages behind a sign-in. It reuses the session saved by the decision-review skill (`node ../decision-review/shoot.mjs --login <url>`). Never ask for or type a password.
- Put `--out` next to the source file, in a folder you'll clean up (e.g. `.live-edit/edits.json`).

The command opens a normal Chrome window, with a separate profile that is not the user's own Chrome, and **waits** until the user clicks **Send to Claude** or closes the window. Run it in the background (`run_in_background`) so you're woken when it ends. If you can't run in the background, use the longest timeout and say so.

Tell the user in one or two lines: the window is open, edit what you like, click **Send to Claude** when done. In Hebrew, mention the button by its Hebrew label, **שליחה לקלוד**.

What the user can do there, in case they ask:
- Click to select, Esc for the parent, Enter for the first child, Tab for the next sibling. The Layers panel shows the page as a tree.
- Drag to reorder inside a stack (flex, grid or normal flow). Cmd/Ctrl-drag to move freely. Arrow keys nudge by 1px, Shift+arrows by 10px.
- Handles resize (Shift keeps the ratio). Double-click text to edit it.
- The Design panel sets position, size, auto layout (direction, gap, alignment), padding, margin, opacity, radius, fill, gradient, stroke, shadow, blur, font, size, weight, line height, letter spacing, alignment, case and text color, plus src and alt on images. Drag a field's label to scrub its value, like in Figma.
- Duplicate (Cmd+D), hide, delete, Cmd+Z / Shift+Cmd+Z. **Interact** mode lets them click through the page normally.
- A panel covering part of the page folds into a small tab when its header is clicked. Cmd+\\ hides both panels.
- **Intent & interaction** under each element: what it should do ("lifts on hover", "opens the pricing drawer", "same change on all cards"). There is also a note for the whole screen.

## Reading edits.json

```json
{
  "status": "sent",
  "screenshots": { "before": "edits-before.png", "after": "edits-after.png" },
  "pages": [{
    "url": "file:///…/index.html",
    "note": "Calmer overall, more air between sections",
    "elements": [
      { "selector": "h1.title", "name": "h1.title “Clear pricing”",
        "changes": [
          { "type": "style", "property": "font-size", "before": "32px", "after": "48px" },
          { "type": "text", "before": "Simple pricing", "after": "Clear pricing" } ] },
      { "selector": "div.card:nth-of-type(2)", "name": "div.card",
        "changes": [ { "type": "style", "property": "border-radius", "before": "8px", "after": "20px" } ],
        "note": "lift 4px on hover, apply to all cards" },
      { "selector": "div.card:nth-of-type(3)", "changes": [
          { "type": "reorder", "parent": "div.cards", "fromIndex": 2, "toIndex": 0, "nowBefore": "div.card:nth-of-type(1)" } ] }
    ],
    "css": "h1.title {\n  font-size: 48px;\n}\n…"
  }]
}
```

- `status`: `sent` (clicked Send), `closed` (closed the window; the edits are still there, so treat it like sent and mention it), `timeout`, or `editing`.
- Selectors always describe the **original** page, before any reorder or duplicate, so they match the source.
- Change types: `style`, `text`, `move` (a `translate` from dragging or nudging), `reorder`, `duplicate` (`of` is the original), `hide`, `delete`, `attribute`.
- `before` is the computed value, colors are hex. `css` is the style changes as one block, for reference only.
- Look at both screenshots before you touch the code. They show what the user was aiming for better than the numbers do.

## Building it into the code

The editor applies everything as inline styles. Never ship it that way. Translate the intent into the code the way a good front-end developer would:

1. **Find the real rule.** Change the existing CSS rule, token or component prop that sets the value, not the element's `style`. If the value is a design token (`var(--space-4)`, a Tailwind class), use the nearest token and say if there isn't an exact one.
2. **One instance or all of them?** If the user changed one of several identical elements (one card of three), apply it to the shared class and say so in one line, unless the note says otherwise or they gave different instances different values. Then keep it per instance.
3. **Moves become layout.** A `move` is the user showing where something should sit. Turn it into margin, gap, padding, alignment or order. Keep a `translate` only for overlap or decoration they clearly wanted.
4. **Reorder, duplicate and delete** change the markup in the source. **Hide** means keep it in the code but hidden: ask whether for good or only on some breakpoint, if that's unclear.
5. **Text** changes go into the source copy, or into the strings file if the project has one.
6. **Intent and interaction notes** are part of the request. Build them: hover, focus and active states, transitions (150–250 ms, ease-out, `transform` and `opacity` only), click behavior, open and close states. Respect `prefers-reduced-motion`, keep everything keyboard-reachable, and keep focus visible. If a note is ambiguous, build the most likely reading and say what you chose.
7. **Live URL without the source here?** If the repo isn't in this session, don't guess. Write the changes as an override stylesheet plus a short list for the markup changes, and ask where the source lives.
8. **Check it.** Render the result and compare it with `edits-after.png`. With the decision-review skill installed: `node ../decision-review/shoot.mjs file://<abs path> check.png --full`. Then delete the check image.

Reply with a short list per element: what changed and where in the code. One line for any interaction you built, one for anything you interpreted. If it was a claude.ai artifact, republish it.

## Another round

Run `edit.mjs` again on the updated file. Each run starts clean, and the previous `edits.json` is overwritten, so read it first. When you're done, delete the `edits*.json` and screenshot files unless the user wants them kept.

## Privacy

Everything stays on the user's machine. The editor makes no network calls. Chrome runs with its own temporary profile, deleted when the window closes, or the saved sign-in profile with `--logged-in`.
