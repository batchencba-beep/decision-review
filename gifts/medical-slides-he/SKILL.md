---
name: medical-slides-he
description: Builds clean, professional Hebrew (RTL) presentation slides as a Claude artifact, for medical treatments, clinics, procedures, patient education and health talks. Uses a fixed design system: a 16:9 canvas, a strict type scale (title, subtitle and body in a fixed ratio), 12 approved layouts, one medical icon set, rules for image placement, and a quality check before delivery. Use whenever the user asks for a presentation, deck, slides, מצגת, שקופיות, סליידים, or asks to fix or redesign an existing deck, especially in Hebrew or on a medical or health topic.
---

# Hebrew medical slides

Build slides that look designed, not generated. The template already contains the whole design system. Fill it in; do not invent a new style.

## Workflow (always in this order)

1. **Understand the content.** If the user has not said so, ask in one short message: who the audience is (patients, doctors, management, investors), how long the talk is, and whether they have images, a logo or brand colors. If they already gave enough, skip this.
2. **Write the outline first, in chat, as a short table:** slide number, layout name, title, one line of content. One message per slide. A typical deck is 8 to 14 slides. Let the user approve or adjust the outline before you build, unless they asked for a finished deck straight away.
3. **Build from the template.** Read `assets/deck-template.html`. Copy it whole into an HTML artifact, delete the example slides between the `EXAMPLE DECK` markers, and write the new slides using only the layouts and classes it defines. Keep every token, the icon sprite, the controls and the script.
4. **Run the quality check** in `references/checklist.md` slide by slide, fix what fails, then deliver.
5. **Deliver** with one line on how to use it: arrows or the buttons to move between slides, `G` toggles the grid, print to PDF exports each slide as a page. Mention any image placeholders the user still needs to fill.

If the session offers a dedicated Slides artifact type, the same rules (type scale, layouts, icons, writing rules, checklist) apply to its content; follow its own format and skip the template.

## The design system (summary; full rules in `references/design-rules.md`)

- **Canvas:** 1920×1080, margins 120px at the sides, 96px at the top. Content sits on a 12-column grid. Never place anything by eye with custom `position`, `margin` or `top` values.
- **Type scale, fixed:** cover/section title 96 · slide title 64 · subtitle 32 · card heading 34 · body 28 · card/table text 24 · source/footer 19. Title to subtitle is always 2:1. Never set a `font-size` inside a slide; use the classes.
- **Every content slide has the same anatomy:** kicker (short label) → title → optional subtitle → body → footer. Titles start at the same spot on every slide, so the deck feels steady when you click through.
- **One idea per slide.** A title is a statement of 3 to 8 words that says the point, not a topic label ("שיקום מלא תוך 6 חודשים", not "שיקום"). At most 5 items in a list, 4 cards, 5 steps, 3 stats. More content means more slides, never smaller text.
- **Images:** one per slide at most, only in the `cover` (40% bleed) and `text-image` (5 of 12 columns) layouts, always `object-fit: cover` inside the `.img` frame. Never use stock-photo URLs you have not been given: they break or show the wrong thing. If the user has no image, use the labeled placeholder (`.img.placeholder`) with an exact description of the photo to add, or choose a layout without an image.
- **Icons:** only from the sprite in the template (`<svg class="icon"><use href="#i-NAME"/></svg>`). One icon per item, the same size within a slide, always inside a `.chip` or next to text. Never use emoji, never mix in another icon set, never use an icon as decoration with no meaning. If no icon fits, use none.
- **Color:** teal primary for numbers, icons and highlights. The amber accent appears at most once per slide. Red (`--danger`) only for warnings and contraindications. Section dividers are the only full-color backgrounds.

## Hebrew and RTL (non-negotiable)

- `dir="rtl"` and `lang="he"` on the page (already in the template). Text aligns right. Layouts flow right to left: the first card, step or column is on the right.
- Numbers, percentages, dates, doses, phone numbers, emails and English terms go inside `<span class="num">…</span>` so they don't jump around in the sentence.
- No italics and no letter-spacing on Hebrew. No English in ALL CAPS in the middle of Hebrew text.
- Forward arrows point left (`#i-arrow-next`). Do not mirror icons that have no direction (heart, pill, clock, check).
- Use ״ and ׳ for Hebrew abbreviations (ד״ר, מ״ג). Prefer natural spoken Hebrew over translated phrasing.

## Medical content rules

- Every statistic, success rate or clinical claim needs a source line (`.source`). If the user did not give one, write `מקור: [להשלים]` and tell them. Never invent numbers.
- No promises of results ("מבטיח", "100% הצלחה"). Use careful wording: "רוב המטופלים", "במחקרים נמצא".
- Warnings and contraindications get the `.callout` box, never small grey text.
- Patient photos, testimonials and before/after images only with a note about consent. Never put identifying patient details on a slide.
- Doses and units are always written in full with the unit: <span class="num">500 מ״ג</span>, not "500".

## Files

- `assets/deck-template.html`: the template, with all 12 layouts as a working example deck. Read it before building.
- `references/design-rules.md`: full rules per layout: when to use it, limits, and what breaks it.
- `references/checklist.md`: the check to run before delivery.
