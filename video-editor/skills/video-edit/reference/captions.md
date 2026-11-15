# Captions

Animated, word-by-word, rendered by Remotion as a transparent layer over the picture.

## Rules (enforced by captions.py, checked by QA)

| Rule | Value | Why |
|---|---|---|
| Words per chunk | 1–3 | Read in one glance while watching a face |
| Characters per chunk | ≤ 16, one line | Two lines double the reading time |
| Breaks | pause > 0.35 s, sentence punctuation, between script beats, around emphasis words | Chunks follow the rhythm of speech |
| Lead | chunk appears 2 frames before its first word | Slightly early reads as snappy; late reads as broken |
| Hold | ≥ 0.4 s; gaps < 0.3 s are bridged | No flicker |
| Active word | brand highlight colour, slight scale | Guides the eye; the viewer's eye follows the voice |
| Spelling | from the SCRIPT where the take aligned, timing from the audio | Whisper writes "4%" where the script says "ארבעה אחוזים", and misspells names |
| Fillers | hard fillers never captioned | |
| Punctuation | commas and full stops dropped, ? and ! kept | |

## Layout

- Vertical centre at `position_y` = 0.64 of the height (safe band 0.25–0.70). Move it up (0.55) when
  the subject is framed low or something important sits in the bottom third. Never below 0.70: the
  caption bar and the description cover it.
- Horizontally centred inside 6%–84% of the width: the like/comment/share column sits on the right in
  every language.
- Font size `size` = 0.074 × width (≈ 80 px at 1080). Bigger (0.085) for short punchy reels, smaller
  only if long words wrap.
- Heebo 800 with a black stroke and a soft shadow: readable on any background.

## Hebrew and right-to-left

- Direction comes from the brief language. Words flow right to left. Each word is isolated
  (`unicode-bidi: isolate`), so English words and numbers inside a Hebrew line keep their own order:
  "עם AI ב-2026" renders correctly.
- In the QA caption frames, check that the first spoken word is on the RIGHT.
- Niqqud is preserved if the script has it; don't add it.

## Changing captions in a revision (EDL `captions`)

```json
"captions": {
  "enabled": true,
  "style": {"size": 0.074, "position_y": 0.64, "max_words": 3, "max_chars": 16,
            "color": "#FFFFFF", "highlight": "#FFD60A", "stroke": "#000000",
            "font": "Heebo", "font_weight": 800, "animation": "pop", "lead_frames": 2, "min_hold": 0.4},
  "overrides": [{"find": "ארבעה אחוזים", "replace": "4%"}],
  "emphasis": ["חינם"],
  "locked": false,
  "chunks": []
}
```
- `overrides` replace a word or phrase, keeping its timing. Use them for brand names, numbers as
  digits, or slang.
- `emphasis` words get their own chunk, bigger and fully highlighted. Use 1–3 per reel at most.
- `chunks` are regenerated on every build. To hand-edit chunks, set `"locked": true` first, and know
  that timing changes in segments will then NOT move the captions. Avoid it.
- Brand font: set `style.font` to its family name and `style.font_file` to a .ttf/.woff2 path in the job folder.
