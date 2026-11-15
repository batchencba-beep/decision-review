# edl.json — the Edit Decision List

`edits/<version>/edl.json` is the single source of truth for a draft. Edit it with your file tools, then
`build.py`. Times are **seconds**. Segment `in`/`out` are SOURCE times in that asset; cutaway `at` and
caption times are OUTPUT times. Everything is snapped to the 30 fps frame grid at build.

```json
{
  "version": "v2",
  "revised_from": "v1",
  "canvas": {"width": 2160, "height": 3840, "fps": 30},
  "segments": [
    {"id": "s1", "asset": "th1", "in": 6.6667, "out": 9.5333, "beat": 0,
     "zoom": 1.0, "anchor": [0.5, 0.4], "reason": "hook, take 2 of 2 — cleaner than take 1"},
    {"id": "s2", "asset": "th1", "in": 14.6, "out": 19.0333, "beat": 1,
     "zoom": 1.2, "anchor": [0.5, 0.35], "reason": "beat 1; punch-in hides the jump cut"}
  ],
  "cutaways": [
    {"id": "c1", "asset": "bank", "beats": [1], "at": null, "duration": null,
     "src_in": 0.0, "trim_start": 0.4, "trim_end": 0.0, "reason": "illustrates the rate cut"}
  ],
  "captions": {"enabled": true, "style": {}, "overrides": [], "emphasis": [], "locked": false, "chunks": []},
  "audio": {"fade_ms": 12},
  "notes": []
}
```

## Segments — the spoken track, in playback order

| Field | Meaning |
|---|---|
| `asset` | an a_roll asset id |
| `in`, `out` | source seconds. The build snaps them out of words, into the quietest 5 ms within ±40 ms, onto a frame. A boundary inside a word is an error unless snapping can move it. |
| `beat` | script beat index (used to anchor cutaways and for your own bookkeeping) |
| `zoom` | 1.0–1.5 punch-in. Refused if fewer than 1080 source pixels would remain across the frame (on a 1080p source, no zoom at all). |
| `anchor` | `[x, y]` of the zoom/crop centre as fractions of the frame. Faces sit around y = 0.35–0.45. |
| `reason` | why this piece is here. Always fill it. |

Order = playback order. To move a beat, move its segments. Two segments from the same take with a short
gap = a pause removed. The output timeline is printed by `validate_edl.py`.

## Cutaways — picture only, over the spoken track

Anchor them to beats (`beats`) **or** give an explicit `at` + `duration` (output seconds). `src_in`
picks where inside the clip to start. `trim_start`/`trim_end` shorten a beat-anchored cutaway at either
end. They are cover-fitted to the canvas; upscaling over 2× is refused (find a bigger source). The
speech keeps playing underneath.

## Captions
See [captions.md](captions.md).

## Revision recipes

| Note from the user | EDL operation |
|---|---|
| "Faster / tighter" | Lower the pause tolerance: re-run `autocut.py --gap 0.22 --pad 0.07 --version vN` into a fresh version, then re-apply your manual choices; or shave segment `in`/`out` by hand. |
| "Cut the line about X" | Find the beat (quoted words → `analysis.json` words → beat). Remove its segments; check the cutaways anchored to it. |
| "Remove the word X at 0:12" | Split the segment around the word: `out` = word start, new segment `in` = word end. Build snaps both. |
| "Use the other take" | Replace the segment's `in`/`out` with that take's `start`/`end` from `analysis.json`; update `reason`. |
| "Start with the second sentence" | Reorder segments. Check the hook rule (the first word ≤ 0.3 s). |
| "Too long" | Drop the beat with the weakest `intent` first; never cut the hook or CTA without asking. |
| "Caption says X, should be Y" | `captions.overrides: [{"find": "X", "replace": "Y"}]`. |
| "Captions bigger / higher" | `captions.style.size` 0.085; `position_y` 0.55. |
| "Highlight the word X" | `captions.emphasis: ["X"]`. |
| "No captions" | `captions.enabled: false`. |
| "Show the AI clip earlier / longer" | Adjust `trim_start` / `trim_end`, or switch to explicit `at` / `duration`. |
| "Jump cut at 0:08 is jarring" | Add `zoom: 1.15–1.25` to the segment after the cut, or cover the cut with a cutaway. |
| "Too zoomed / cropped" | `zoom: 1.0`, or move `anchor`. |

After any edit: `validate_edl.py <job> <v> --snap` to see the new timeline, then `build.py <job> <v>`.
