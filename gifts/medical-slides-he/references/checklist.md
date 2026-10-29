# Check before delivery

Go through every slide. Fix each failure in the code, then check that slide again. Don't deliver while anything fails.

## Structure
- [ ] Every slide uses exactly one approved `data-layout`.
- [ ] No inline `font-size`, `color`, `margin`, `top` or `position` was added. Only `--n` is set inline.
- [ ] No layout repeats more than 3 slides in a row.
- [ ] Reading only the titles tells the story of the deck.

## Hierarchy and text
- [ ] Every title is a statement of 3 to 8 words that fits on at most 2 lines.
- [ ] The subtitle adds information and does not repeat the title.
- [ ] The layout's limits are met (number of items and words, from `design-rules.md`).
- [ ] Items of the same kind have the same structure and similar length: card to card, step to step, column to column.
- [ ] Nothing overflows: in the rendered artifact, no red outline and no "⚠ חריגה" warning in the bottom bar. If you can't see the render, count words against the limits; when in doubt, cut text or split the slide.

## Images and icons
- [ ] At most one image per slide, only in `cover` or `text-image`, inside `.img`.
- [ ] No image URL the user didn't provide. Every placeholder describes the exact shot.
- [ ] Every icon comes from the sprite, means something for its item, and sits in a `.chip` or next to text. No emoji anywhere.
- [ ] Within a slide, every item has an icon or none does.

## Hebrew and RTL
- [ ] Every number, percentage, date, dose, phone number, email and English word is inside `.num`.
- [ ] The first item is on the right. Forward arrows point left.
- [ ] No italics, letter-spacing or ALL CAPS on Hebrew text.

## Medical
- [ ] Every number and clinical claim has a source, or `[להשלים]` and you told the user.
- [ ] No promised results. Warnings use `.callout`.
- [ ] Testimonials and patient photos carry a consent note, and no patient can be identified.

## Delivery message
One short paragraph: how many slides, which placeholders and sources the user still has to fill in, and how to move between slides (arrows or buttons; `G` toggles the grid; print to PDF for a file).
