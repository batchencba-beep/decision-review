# Fix recipes

Every fix keeps the user's colors, fonts and layout idea. "Their norm" means the value most of their slides already use (`deck.norm` in the audit report, or what you wrote down in step 3).

## Overlaps

**overlap-text, overlap-image, overlap-icon, overlap-media.** Two things share space that should not.
- Usual cause: absolute positioning (`position:absolute` with `top`/`left` set by hand) on elements that should flow. Fix: put the elements of that region in a flex or grid container with a `gap`, so they can't collide when text grows.
- Title over an image: give the text and the image separate columns or rows using their own split (see Images). If the design puts text over a photo on purpose (hero/cover), keep it, add a scrim in their colors behind the text (a gradient from their background color at 70–85% opacity to transparent) and keep the text inside the calm part of the image.
- Layering is wrong (a decorative shape covers text): set `z-index` so the order is background < decoration < image < text, and `pointer-events:none` on decoration.
- Never fix an overlap by shrinking text below their body size.

**out-of-slide, clipped, image-out.** Content runs past the slide or is cut off by `overflow:hidden`.
- Remove fixed `height` on text boxes; let them grow inside a flex column.
- If it still doesn't fit: reduce spacing first (to their smallest gap), then one step down in their own type scale, then (last) split or shorten, and list it as a content change.
- Long Hebrew words in narrow columns: widen the column within the grid rather than adding hyphenation.

## Proportions

Targets below are ranges. If their deck is already inside a range, keep their value. If not, move to the nearest edge of the range, so the change stays small.

| Relationship | Target |
|---|---|
| Title : body | 1.8 to 3 times |
| Subtitle | 0.5 to 0.65 of the title, and at least 1.2 times the body |
| Title → subtitle gap | 0.3 to 0.5 of the title size |
| Header → content gap | at least 1 title size |
| Side margins | at least 5% of the slide width, the same on every slide |
| Text-only column width | 45 to 75 characters per line |
| Image beside text | image 40 to 50% of the content width; text column at least 45% |
| Inline icon (next to a line of text) | 1 to 1.3 times the font size of that text |
| Feature icon (on a card or list item) | 2 to 3 times the body size, the same on every card |

**weak-hierarchy** (title too close to body): raise the title to their norm title size, or use their bolder weight. Don't touch body size.
**subtitle-too-close** (subtitle almost as big as the title, or almost the body): set it inside the subtitle range and give it their secondary color or a lighter weight if the deck already uses one.
**title-too-big**: bring it down to their norm, or let it wrap to 2 balanced lines (`text-wrap:balance`).
**too-many-sizes**: snap every size on the slide to the nearest of their 4 to 5 main sizes (title, subtitle, body, small, caption).
**text-too-small**: raise to their caption size at least; on a 1080px slide nothing should be under ~18px.
**crowded**: increase spacing within their scale first; then split the content into two slides of the same layout.
**title-size-inconsistent, title-position-inconsistent, body-size-inconsistent**: one shared class or component for the slide header and body, with their norm values, used by every content slide. Cover, section and closing slides may differ on purpose; leave those alone.

## Images

**image-stretched**: `object-fit:cover` plus an explicit box size or `aspect-ratio`; set `object-position` so faces or the subject stay in frame.
**image-broken**: point to an image the user gave you. If there is none, use a placeholder in their style (their surface color, their radius, with a short label of what belongs there). Never swap in a random stock URL.
**image-near-edge**: decide one of two. Either bleed (touch the slide edge, radius 0 on that side) or sit on their margin line. Nothing in between.
**image-tiny**: grow it to their usual image share, or remove it if it's decoration with no meaning.
- Same kind of image, same treatment across the deck: one radius, one border/shadow style, one split ratio for text+image slides (use the one they use most).

## Icons

**emoji-icon**: replace with an icon from the set the deck already uses most, in the same style. If the deck has no icon set, use Lucide-style outline icons (24 grid, 2px stroke, round caps), drawn inline as SVG.
**icon-styles** / **icon-styles-deck** (filled mixed with outline, different stroke widths, different libraries): unify to the style that most of their icons already use.
**icon-sizes**: one size per role (inline, list or card, hero), from the targets above.
- Every icon in a group sits in the same container (all in circles or none), in the same color, and means something for its item. Remove icons that are pure decoration in a list where the others carry meaning, or add a matching one so the group is complete.

## Alignment and margins

**misaligned**: a few pixels off is the "sloppy" look. Snap both to the same edge: give siblings the same container and alignment, and remove one-off margins.
**tight-margin**: move content inside their side margin. If slides use different margins, set one value for all of them.
- In RTL, the strong edge is the right one: titles, body and lists should share one right edge on every content slide.
