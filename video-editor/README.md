# video-editor

A Claude Code plugin with one agent and one skill that edit short-form vertical video: Reels, TikTok and Shorts.

- **Agent `video-editor`**: the editor. Your Reels Agent (or you) hands it a job folder, and it returns a
  finished draft, an edit log and a QA contact sheet, then handles revision rounds.
- **Skill `video-edit`**: the editor's know-how and tools: the pipeline, the editorial rules, the quality
  bar, a Remotion caption template with right-to-left support, and self-QA.

```
brief.json + footage ─▶ probe ─▶ ingest ─▶ transcribe ─▶ analyze ─▶ autocut ─▶ [agent edits the EDL]
                                                                                    │
                     ┌───────────── revision round (new version, cached segments) ◀─┤
                     ▼                                                              │
   build: snap ─▶ captions ─▶ cut ─▶ render captions + composite ─▶ export ─▶ QA ───┘
```

## What it does

- Finds every take of every script line, keeps the best one, and drops false starts and off-script talk.
- Closes pauses, removes fillers (אממ, אה, um), and keeps the hook inside the first 3 seconds.
- Makes cuts frame-exact, places them in the quietest 5 ms between words, and adds micro-fades so cuts never click.
- Adds animated word-by-word captions. Hebrew renders right to left, English words and numbers inside a Hebrew line stay in the right order, and spelling comes from the script.
- Lays AI clips over the beats they illustrate, frame-accurately.
- Converts iPhone footage properly: variable frame rate → constant 30 fps, and HDR (HLG) → Rec.709 tone-mapping.
- Keeps everything in ProRes until a single final encode. Exports at 1080 for Instagram and 4K for TikTok/Shorts, normalised to -14 LUFS.
- Runs self-QA before delivery: format, loudness, black frames, a re-transcription of the export to catch clipped words, caption sync, and frames for the agent to look at.

## Install

```bash
/plugin marketplace add batchencba-beep/decision-review
/plugin install video-editor@batchenba
```

Then, once per machine, run `skills/video-edit/scripts/setup.sh` (or let the agent run it on first use).
It needs ffmpeg ≥ 6, Python ≥ 3.10 and Node ≥ 18 (on macOS: `brew install ffmpeg node`). It installs
faster-whisper and Remotion and downloads the Hebrew Whisper model (~1.6 GB).

## Use

Make a job folder:

```
my-reel/
  brief.json      script + assets + target  (see skills/video-edit/reference/brief.md)
  assets/IMG_0001.MOV
  assets/veo_clip.mp4
```

Then ask Claude: *"Edit the reel in ./my-reel"*. For a revision: *"In my-reel: cut the line about
prices and make the captions bigger"*.

To connect your Reels Agent, have it write `brief.json` in this format and end with
"hand the job folder to the video-editor agent".

## Shoot for it

On the iPhone, go to Settings → Camera → Record Video and choose **4K at 30 fps** with **HDR Video off**. Lock exposure and focus, use a lavalier mic,
and leave a beat of silence before and after each line.
