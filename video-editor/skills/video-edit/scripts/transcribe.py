#!/usr/bin/env python3
"""Step 3 — word-level transcript for every a_roll asset.

usage: transcribe.py <job> [--model NAME] [--force]

Hebrew uses ivrit.ai's fine-tuned Whisper (large-v3-turbo, CTranslate2), which is far more accurate on
Hebrew than stock Whisper. Other languages use stock large-v3-turbo. Override with --model or the
VIDEO_EDIT_WHISPER_MODEL env var (e.g. a smaller model for quick drafts).

Whisper word timestamps are typically 50–150 ms off. Each word boundary is therefore refined against
the audio energy envelope (onset / offset detection), which is what captions and cut-snapping use.
Raw timestamps are kept as raw_start / raw_end.

Output: work/transcripts/<id>.json  {words:[{i,text,start,end,prob,raw_start,raw_end}], ...}
"""
import os
import sys
import time

from common import Envelope, Job, load_wav16k, save

MODELS = {"he": "ivrit-ai/whisper-large-v3-turbo-ct2"}
DEFAULT_MODEL = "large-v3-turbo"
# Priming with disfluencies makes Whisper write fillers instead of silently dropping them,
# so autocut can see and remove them.
PROMPTS = {"he": "אממ... אה, כן. אז, אה, בעצם", "en": "Umm, uh, so, like, you know."}

_model_cache = {}


def get_model(name: str):
    from faster_whisper import WhisperModel
    if name not in _model_cache:
        threads = max(1, (os.cpu_count() or 4))
        _model_cache[name] = WhisperModel(name, device="auto", compute_type="int8", cpu_threads=threads)
    return _model_cache[name]


def transcribe_wav(wav, language: str, model_name: str | None = None) -> dict:
    name = model_name or os.environ.get("VIDEO_EDIT_WHISPER_MODEL") or MODELS.get(language, DEFAULT_MODEL)
    model = get_model(name)
    t0 = time.time()
    # pass samples, not a path: avoids faster-whisper's PyAV decoder (version-fragile)
    segments, info = model.transcribe(
        load_wav16k(wav), language=language, word_timestamps=True, beam_size=5, vad_filter=False,
        condition_on_previous_text=False, initial_prompt=PROMPTS.get(language),
    )
    words, segs = [], []
    for s in segments:
        segs.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()})
        for w in s.words or []:
            t = w.word.strip()
            if not t:
                continue
            words.append({"text": t, "raw_start": float(w.start), "raw_end": float(w.end),
                          "prob": round(float(w.probability), 3)})
    refine(words, Envelope(wav))
    for i, w in enumerate(words):
        w["i"] = i
    return {"language": language, "model": name, "duration": round(info.duration, 3),
            "elapsed": round(time.time() - t0, 1), "words": words, "segments": segs}


def silences(env: Envelope, thr: float, min_len: float = 0.15) -> list[tuple[float, float]]:
    out, start = [], None
    for i, v in enumerate(env.db):
        if v < thr:
            if start is None:
                start = i
        elif start is not None:
            if (i - start) * env.HOP >= min_len:
                out.append((start * env.HOP, i * env.HOP))
            start = None
    if start is not None and (len(env.db) - start) * env.HOP >= min_len:
        out.append((start * env.HOP, len(env.db) * env.HOP))
    return out


def refine(words: list[dict], env: Envelope, rise_db: float = 14.0):
    """Correct Whisper word boundaries against the audio.

    1. Silence barriers. Whisper habitually glues a pause onto the NEXT word ("בוא" = 0.9 s of silence
       plus the word) and leaves the previous word's tail inside that next word. No word may contain a
       pause ≥ 150 ms: the word starts after the pause, and the speech before the pause goes to the
       previous word.
    2. Onset/offset. Start = first loud 5 ms hop (minus 30 ms pre-roll for soft attacks such as ה/ש/פ),
       end = last loud hop (+40 ms natural decay).
    """
    floor = env.noise_floor()
    thr = floor + rise_db
    hop = env.HOP
    n = len(env.db)
    sil = silences(env, thr)
    s_ = [w["raw_start"] for w in words]
    e_ = [w["raw_end"] for w in words]
    for k in range(len(words)):
        inside = [(a, b) for a, b in sil if a > s_[k] + 0.02 and b < e_[k] - 0.02]
        if inside:
            a, b = inside[-1]
            if e_[k] - b >= 0.08:          # the word itself is after the pause
                s_[k] = b
                if k and e_[k - 1] <= a + 0.05:
                    e_[k - 1] = max(e_[k - 1], a)
            else:                           # the word is before the pause; next word owns what follows
                e_[k] = a
        # a pause that straddles the word's start or end trims it
        for a, b in sil:
            if a <= s_[k] < b < e_[k]:
                s_[k] = b
            if s_[k] < a < e_[k] <= b:
                e_[k] = a
    for k, w in enumerate(words):
        prev_end = e_[k - 1] if k else 0.0
        next_start = s_[k + 1] if k + 1 < len(words) else env.duration
        s, e = s_[k], e_[k]
        a = max(prev_end, s - 0.15)
        i, stop = int(a / hop), min(n, int(max(s + 0.10, e - 0.05) / hop))
        while i < stop and env.db[i] < thr:
            i += 1
        start = max(a, i * hop - 0.03) if i < stop else s
        b = min(next_start, e + 0.20)
        j, stop = min(n - 1, int(b / hop)), max(0, int(min(e - 0.10, start + 0.05) / hop))
        while j > stop and env.db[j] < thr:
            j -= 1
        end = min(b, (j + 1) * hop + 0.04) if j > stop else e
        if end - start < 0.06:  # refinement collapsed the word: keep the corrected span
            start, end = s, e
        w["start"], w["end"] = round(start, 3), round(end, 3)
    # keep words monotonic and non-overlapping
    for k in range(1, len(words)):
        if words[k]["start"] < words[k - 1]["end"]:
            mid = round((words[k]["start"] + words[k - 1]["end"]) / 2, 3)
            words[k - 1]["end"] = max(words[k - 1]["start"] + 0.02, mid)
            words[k]["start"] = max(words[k - 1]["end"], words[k]["start"])
    # Whisper invents text in silence ("תודה רבה.", "Thanks for watching"). A word with no sound
    # under it is marked unvoiced; analyze.py ignores it.
    for w in words:
        w["voiced"] = bool(env.db[int(w["start"] / hop): max(int(w["start"] / hop) + 1, int(w["end"] / hop))].max() > thr)


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    model = None
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]
        args = [x for x in args if x != model]
    job = Job(args[0])
    lang = job.brief["target"]["language"]
    for a in job.a_roll():
        out = job.transcript(a["id"])
        wav = job.wav(a["id"])
        if not wav.exists():
            raise SystemExit(f"{wav} missing — run ingest.py first")
        if out.exists() and "--force" not in sys.argv and out.stat().st_mtime > wav.stat().st_mtime:
            print(f"  {a['id']}: transcript up to date")
            continue
        print(f"  {a['id']}: transcribing ({lang}) ...", flush=True)
        data = transcribe_wav(wav, lang, model)
        data["asset"] = a["id"]
        save(out, data)
        print(f"  {a['id']}: {len(data['words'])} words in {data['elapsed']}s -> {out.name}")
        print("    " + " ".join(w["text"] for w in data["words"])[:400])


if __name__ == "__main__":
    main()
