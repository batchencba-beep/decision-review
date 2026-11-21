# brief.json — the hand-off from the Reels Agent

One file at the root of the job folder. The Reels Agent writes it; the editor reads it and never changes it.

```json
{
  "id": "rate-cut-explainer",
  "script": {
    "hook": "בנק ישראל הוריד את הריבית. הנה מה שזה אומר עליך.",
    "beats": [
      {"text": "הריבית ירדה ברבע אחוז לארבעה אחוזים.", "intent": "the news, fast"},
      {"text": "המשכנתא שלך יכולה להתייקר פחות כבר מהחודש הבא.", "intent": "why it matters"}
    ],
    "cta": "שמרו את הסרטון ותבדקו את הדוח הבא שלכם."
  },
  "assets": [
    {"id": "th1", "path": "assets/IMG_4021.MOV", "type": "talking_head"},
    {"id": "th2", "path": "assets/IMG_4022.MOV", "type": "talking_head"},
    {"id": "bank", "path": "assets/veo_bank.mp4", "type": "ai_clip", "beat_ref": [1]},
    {"id": "avatar", "path": "assets/heygen_cta.mp4", "type": "ai_avatar"}
  ],
  "target": {"platforms": ["instagram", "tiktok"], "max_seconds": 35, "language": "he"},
  "brand": {"caption_font": "Heebo", "primary": "#FFFFFF", "highlight": "#FFD60A", "stroke": "#000000"},
  "style": {"captions": "bold", "zoom": true, "notes": ""}
}
```

| Field | Required | Meaning |
|---|---|---|
| `script.hook` / `beats[]` / `cta` | recommended | The lines in order. Beat **indices** count hook = 0, then beats, then CTA. Without a script the edit is unscripted: the whole transcript is one beat (pauses and fillers still go). |
| `script.mode` | no (`verbatim`) | `verbatim`: the speaker reads the lines word for word; takes are matched against them and caption spelling comes from the script. `points`: the lines are talking points and the speaker improvises around them; takes are found by repetition (a sentence said again within the next three replaces the earlier try), each kept sentence is tagged with the point it covers, sentences that cover no point are flagged `off_point`, and uncovered points are listed as `missing_point`. Captions use the transcript (fix spelling with overrides). |
| `beats[].intent` | no | Why the beat exists. Helps you decide which beat to drop for length. |
| `assets[].path` | yes | Relative to the job folder. Originals are never modified. |
| `assets[].type` | no | `talking_head` (default), `ai_avatar`, `ai_clip`, `broll`. |
| `assets[].role` | no | Derived from `type`: `a_roll` (carries speech: talking_head, ai_avatar) or `b_roll` (picture only, muted). Set it explicitly to override. |
| `assets[].beat_ref` | for b_roll | Beat indices the clip illustrates. autocut lays it over those beats. |
| `target.max_seconds` | no (60) | Hard ceiling. |
| `target.platforms` | no (all) | `instagram`, `tiktok`, `shorts`. A 4K TikTok/Shorts export is added when the canvas is 4K. |
| `target.language` | no (`he`) | Transcription model and caption direction (he/ar/yi/fa → right-to-left). |
| `brand.*` | no | Caption colours and font. `font_file` (path in the job folder) for any font other than Heebo. |
| `style.captions` | no (`bold`) | `bold` big outlined captions with a coloured active word and a pop-in; `quiet` smaller, no outline, soft shadow, upcoming words dimmed, fade-in; `none` no captions. |
| `style.zoom` | no (`true`) | `false` forbids punch-ins: the validator refuses any zoom. Hide jump cuts with cutaways or better cut points. |
| `style.notes` | no | Free-text editing direction ("quiet, warm, designed"). Read it and follow it. |

## When to stop and ask

- No a_roll asset, or a_roll with no audio.
- The footage plainly doesn't match the script (a different video).
- `max_seconds` impossible without dropping more than one beat.
Everything else, decide and note it in the edit log.

## Hand-off packages

An upstream agent that cannot write files (a Claude chat project) sends a **hand-off package**: a message
that contains the brief JSON in a code block. Write it to `<job>/brief.json` yourself. Match each asset
`path` to the files actually in `assets/` (by name, then by type and duration); if two files could fit
one asset, ask. Never invent footage that isn't there: a missing asset is a blocker to report.
