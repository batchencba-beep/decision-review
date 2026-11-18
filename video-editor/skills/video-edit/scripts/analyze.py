#!/usr/bin/env python3
"""Step 4 — line the transcript up against the script.

usage: analyze.py <job>

For every script beat (hook, beats, CTA) finds every TAKE of it in the footage — the speaker often says a
line two or three times — and scores each take. Also lists pauses, unworded sounds and filler words.
This is evidence for the editor; it decides nothing. autocut.py turns it into a first EDL, and the agent
overrules it wherever its judgment differs.

Take score = similarity of the spoken words to the script line (0..1). Quality notes per take:
  pauses    internal pauses > 0.6 s     fillers   filler words inside the take
  prob      mean recognition confidence  wps       speaking rate (words / second)

Writes work/analysis.json.
"""
import sys
from difflib import SequenceMatcher

from common import Envelope, Job, is_filler, load, norm_word, save, script_beats, tc, tokenize

MIN_SCORE = 0.55          # below this a span is not considered a take of the beat
PREFER_LATER_WITHIN = 0.06  # editors' rule: the last good take is usually the keeper
GAP_MIN = 0.25


def stream(job: Job) -> list[dict]:
    words = []
    for a in job.a_roll():
        t = load(job.transcript(a["id"]))
        for w in t["words"]:
            if not w.get("voiced", True):
                print(f"  ignoring unvoiced (hallucinated) word '{w['text']}' at {tc(w['start'])}")
                continue
            words.append({**w, "asset": a["id"], "key": norm_word(w["text"])})
    for gi, w in enumerate(words):
        w["g"] = gi
    return words


def find_takes(beat_keys: list[str], words: list[dict]) -> list[dict]:
    L = len(beat_keys)
    if L == 0:
        return []
    heads = set(beat_keys[: min(3, L)])
    keys = [w["key"] for w in words]
    cands = []
    for i in range(len(words)):
        if keys[i] not in heads:
            continue
        best = None
        for n in range(max(1, int(L * 0.6)), int(L * 1.5) + 2):
            j = i + n
            if j > len(words):
                break
            win = words[i:j]
            if len({w["asset"] for w in win}) > 1:
                break
            r = SequenceMatcher(None, beat_keys, keys[i:j], autojunk=False).ratio()
            if best is None or r > best[0] + 1e-9:
                best = (r, i, j)
        if best and best[0] >= MIN_SCORE:
            cands.append(best)
    # non-maximum suppression: best-scoring non-overlapping spans
    cands.sort(key=lambda c: -c[0])
    chosen = []
    for r, i, j in cands:
        if all(j <= ci or i >= cj for _, ci, cj in chosen):
            chosen.append((r, i, j))
    chosen.sort(key=lambda c: c[1])
    return [{"w0": i, "w1": j - 1, "score": round(r, 3)} for r, i, j in chosen]


SENT_END = (".", "?", "!", "…")


def extend_to_sentence(t: dict, words: list[dict], taken: set[int]) -> dict:
    """Grow a take to whole-sentence edges.

    Whisper may write a line differently from the script ("4%" for "ארבעה אחוזים"), so the best-matching
    window can stop short of the real end of the sentence. Cutting there would clip the speaker
    mid-sentence. Extend forward until sentence punctuation (≤ 4 words, gaps < 0.5 s) and backward
    while the previous word does not end a sentence (≤ 3 words, gaps < 0.3 s).
    """
    w0, w1 = t["w0"], t["w1"]
    asset = words[w0]["asset"]
    k = 0
    while (k < 4 and not words[w1]["text"].endswith(SENT_END) and w1 + 1 < len(words)
           and w1 + 1 not in taken and words[w1 + 1]["asset"] == asset
           and words[w1 + 1]["start"] - words[w1]["end"] < 0.5):
        w1, k = w1 + 1, k + 1
    k = 0
    while (k < 3 and w0 > 0 and w0 - 1 not in taken and words[w0 - 1]["asset"] == asset
           and not words[w0 - 1]["text"].endswith(SENT_END)
           and words[w0]["start"] - words[w0 - 1]["end"] < 0.3):
        w0, k = w0 - 1, k + 1
    return {**t, "w0": w0, "w1": w1, "extended": (w0, w1) != (t["w0"], t["w1"])}


def describe_take(t: dict, words: list[dict]) -> dict:
    span = words[t["w0"]: t["w1"] + 1]
    pauses = sum(1 for a, b in zip(span, span[1:]) if b["start"] - a["end"] > 0.6)
    fillers = sum(1 for w in span if is_filler(w["text"], hard_only=False))
    dur = span[-1]["end"] - span[0]["start"]
    return {**t, "asset": span[0]["asset"], "start": span[0]["start"], "end": span[-1]["end"],
            "first_word": span[0]["i"], "last_word": span[-1]["i"],
            "pauses": pauses, "fillers": fillers,
            "prob": round(sum(w["prob"] for w in span) / len(span), 3),
            "wps": round(len(span) / dur, 2) if dur > 0 else 0,
            "text": " ".join(w["text"] for w in span)}


def pick(takes: list[dict]) -> int | None:
    if not takes:
        return None
    best = max(t["score"] - 0.02 * t["pauses"] - 0.01 * t["fillers"] for t in takes)
    ok = [k for k, t in enumerate(takes)
          if t["score"] - 0.02 * t["pauses"] - 0.01 * t["fillers"] >= best - PREFER_LATER_WITHIN]
    return ok[-1]


def display_text(beat_tokens: list[str], take_words: list[dict]) -> dict:
    """Map transcript words -> script spelling where they align one-to-one (script = spelling authority)."""
    bk = [norm_word(t) for t in beat_tokens]
    tk = [w["key"] for w in take_words]
    out = {}
    for op, a0, a1, b0, b1 in SequenceMatcher(None, bk, tk, autojunk=False).get_opcodes():
        if op == "equal" or (op == "replace" and a1 - a0 == b1 - b0):
            for k in range(a1 - a0):
                out[take_words[b0 + k]["g"]] = beat_tokens[a0 + k]
        elif op == "replace" and a1 - a0 <= 6 and b1 - b0 <= 6:
            # "ב -0 .4 %" heard, "ברבע אחוז" scripted: the first heard word carries the script words
            # (captions spread them over the span's time); the rest of the span shows nothing.
            out[take_words[b0]["g"]] = " ".join(beat_tokens[a0:a1])
            for k in range(b0 + 1, b1):
                out[take_words[k]["g"]] = ""
    return out


def gaps(job: Job, words: list[dict]) -> list[dict]:
    res = []
    by_asset = {}
    for w in words:
        by_asset.setdefault(w["asset"], []).append(w)
    for aid, ws in by_asset.items():
        env = Envelope(job.wav(aid))
        floor = env.noise_floor()
        edges = [(0.0, ws[0]["start"], -1)] + [(a["end"], b["start"], a["i"]) for a, b in zip(ws, ws[1:])] \
            + [(ws[-1]["end"], env.duration, ws[-1]["i"])]
        for s, e, after in edges:
            if e - s < GAP_MIN:
                continue
            lvl = env.level(s, e)
            loud = env.level(s + 0.03, e - 0.03) if e - s > 0.1 else lvl
            kind = "silence" if loud < floor + 9 else "sound"
            res.append({"asset": aid, "after_word": after, "start": round(s, 3), "end": round(e, 3),
                        "dur": round(e - s, 3), "level_db": round(lvl, 1), "kind": kind})
    return res


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    job = Job(sys.argv[1])
    words = stream(job)
    if not words:
        raise SystemExit("no words transcribed — check the a_roll audio")
    beats = script_beats(job.brief)
    scripted = bool(beats)
    if not scripted:
        beats = [{"index": 0, "kind": "unscripted", "text": " ".join(w["text"] for w in words)}]

    out_beats, display, used = [], {}, set()
    used_elsewhere: set[int] = set()
    for b in beats:
        toks = tokenize(b["text"])
        if scripted:
            raw = find_takes([norm_word(x) for x in toks], words)
            spans = {g for t in raw for g in range(t["w0"], t["w1"] + 1)}
            takes = []
            for t in raw:
                own = spans - set(range(t["w0"], t["w1"] + 1))
                takes.append(describe_take(extend_to_sentence(t, words, own | used_elsewhere), words))
        else:
            takes = [describe_take({"w0": 0, "w1": len(words) - 1, "score": 1.0}, words)]
        k = pick(takes)
        for n, t in enumerate(takes):
            t["chosen"] = n == k
            for g in range(t["w0"], t["w1"] + 1):
                used.add(g)
                used_elsewhere.add(g)
        if k is not None and scripted:
            display.update(display_text(toks, words[takes[k]["w0"]: takes[k]["w1"] + 1]))
        out_beats.append({**{x: b[x] for x in ("index", "kind", "text")}, "takes": takes})

    unmatched, run_ = [], []
    for w in words:
        if w["g"] in used:
            if run_:
                unmatched.append(run_)
            run_ = []
        else:
            run_.append(w)
    if run_:
        unmatched.append(run_)

    data = {
        "scripted": scripted,
        "words": [{"g": w["g"], "asset": w["asset"], "i": w["i"], "text": w["text"],
                   "display": display.get(w["g"], w["text"]), "start": w["start"], "end": w["end"],
                   "prob": w["prob"], "filler": is_filler(w["text"], hard_only=False),
                   "hard_filler": is_filler(w["text"])} for w in words],
        "beats": out_beats,
        "gaps": gaps(job, words),
        "unmatched": [{"asset": r[0]["asset"], "start": r[0]["start"], "end": r[-1]["end"],
                       "text": " ".join(w["text"] for w in r)} for r in unmatched],
    }
    save(job.analysis_path, data)

    for b in out_beats:
        print(f"[{b['index']}] {b['kind']}: {b['text'][:70]}")
        if not b["takes"]:
            print("     !! NO TAKE FOUND — line missing from footage or badly misrecognised")
        for t in b["takes"]:
            mark = "★" if t["chosen"] else " "
            print(f"   {mark} {t['asset']} {tc(t['start'])}–{tc(t['end'])} score={t['score']:.2f} "
                  f"pauses={t['pauses']} fillers={t['fillers']} prob={t['prob']:.2f} | {t['text'][:60]}")
    if data["unmatched"]:
        print("off-script speech (dropped by autocut unless you keep it):")
        for u in data["unmatched"]:
            print(f"   {u['asset']} {tc(u['start'])}–{tc(u['end'])}: {u['text'][:80]}")
    snd = [g for g in data["gaps"] if g["kind"] == "sound"]
    print(f"gaps: {len(data['gaps'])} ({len(snd)} with unworded sound — breath, laugh or a missed word)")
    print(f"-> {job.analysis_path}")


if __name__ == "__main__":
    main()
