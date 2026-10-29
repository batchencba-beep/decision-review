# Design rules

Why slides look sloppy, and the rule that prevents each problem:

| Problem | Rule |
|---|---|
| Titles jump around from slide to slide | Same anatomy on every slide: `.head` (kicker, title, subtitle) at the top, `.body`, `.foot`. |
| Title, subtitle and text look about the same size | Fixed scale with big steps: 64 / 32 / 28 / 24. Hierarchy comes from size and weight together: title 800, heading 700, body 400. |
| Text crammed in, or tiny text to fit more | Limits per layout (below). Too much content becomes two slides. |
| Image dropped in at a random size | Images only in fixed frames: 40% bleed on the cover, 5 of 12 columns in `text-image`. |
| Icons that mean nothing, in mixed styles | One sprite, one stroke width, one icon per item, inside a `.chip`. |
| Random colors | Tokens only. Primary for emphasis, the accent once, red only for warnings. |
| Unbalanced empty space | Content aligns to the grid. Empty space is fine when it is on purpose: keep the body aligned to the top or the center as the layout defines. Never stretch text to fill space. |

## Tokens

Change look only in `:root`. To use the user's brand, change `--primary`, `--primary-soft`, `--accent` and `--font`, and check contrast: primary text on white needs at least 4.5:1. Keep everything else.

Spacing scale: 8 · 16 · 24 · 32 · 48 · 64 · 96 (`--s1`…`--s7`). Nothing in between.

## Layouts

Pick one per slide with `data-layout`. Don't create new layouts and don't mix two on one slide. Don't use the same layout on more than 3 slides in a row; vary the rhythm.

| Layout | Use for | Limits |
|---|---|---|
| `cover` | First slide | Title up to 8 words over 2 lines, subtitle 1 to 2 lines, one image or placeholder on the left |
| `section` | Opening a chapter in a deck of 10+ slides | Number + title of up to 4 words + an optional one-line subtitle |
| `text-image` | Explaining one thing that a picture shows: a procedure, a device, the clinic | Up to 4 bullets or 2 short paragraphs (up to 50 words). Image on the left |
| `list` | Instructions, what to bring, symptoms | 3 to 5 items. Each has an icon, a heading of up to 4 words and an optional line of up to 12 words |
| `cards` | Parallel options: treatment types, team, services | 3 or 4 cards (`style="--n:3"` or `4`). Heading up to 3 words, text up to 18 words. Every card gets the same structure |
| `steps` | Treatment process, recovery timeline, patient journey | 3 to 5 steps (`--n`). Each has a time (`.when`), a heading of up to 2 words and a line of up to 10 words |
| `stat` | One number that is the point of the slide | One number, label up to 12 words, required source |
| `stats` | Three key numbers | Exactly 3. Short numbers (up to 4 characters), labels up to 6 words, source in the footer |
| `compare` | Recommended vs avoid, before vs after, option A vs B | 2 columns, 3 to 5 items each, matching lengths |
| `table` | Follow-up schedule, doses, prices, comparisons with exact values | Up to 3 or 4 columns and 6 rows. Short cells. Numbers in `.num` |
| `quote` | Patient testimonial, expert quote | Up to 30 words, with attribution. Testimonials need consent |
| `closing` | Questions, contact details, a call to action | Title + up to 3 contact items with icons |

Callout (`.callout`): for a single warning inside a slide (`list`, `table`, `text-image`). One per slide at most.

## Writing for slides

- Title = the message. Read only the titles in order: they should tell the whole story.
- Subtitle = one sentence that adds context. It does not repeat the title.
- Bullets are phrases, not full sentences, with no full stop at the end. Start each with the key word.
- No paragraph longer than 3 lines. No more than about 40 words of body text on a content slide.
- Use the same terms throughout: if a slide says "מטופל", don't switch to "פציינט" later.

## Images

- Real images: `<div class="img"><img src="..." alt="תיאור"></div>`. Use only images the user uploaded or linked.
- No image available: `<div class="img placeholder"><div><svg class="icon"><use href="#i-image"/></svg><span>תמונה: [exact description]</span></div></div>`. Describe the shot precisely (who, doing what, where, mood) so the user can find or make the right one.
- Medical images: no blood or open wounds unless the audience is clinical; no identifying patient faces without consent; prefer clean, well-lit photos of the clinic, the equipment or people in motion.
- One image per slide. Never put text on top of a photo, apart from the cover.

## Icons available

`heart-pulse` `activity` `stethoscope` `pill` `syringe` `thermometer` `medical` `shield-check` `clipboard-check` `file-text` `calendar` `clock` `user` `users` `eye` `check-circle` `x-circle` `alert` `trending-up` `map-pin` `mail` `phone` `image` `arrow-next` `arrow-prev`

To add an icon the list doesn't have, draw it in the same style: a 24×24 viewBox, stroke only, no fill, stroke-width 2, round caps and joins, as a new `<symbol id="i-NAME">` in the sprite. Never paste a filled icon or one from another set.
