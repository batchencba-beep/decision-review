#!/usr/bin/env python3
"""Caption chunks from the EDL timeline — regenerated on every build unless captions.locked is true.

usage: captions.py <job> <version>      (build.py calls this; run alone to preview chunks)

Rules (see reference/captions.md):
  * 1–3 words per chunk, ≤ 16 characters, one line
  * break on pauses > 0.35 s, after sentence punctuation, between script beats, and around emphasis
    words (shown alone)
  * spelling comes from the SCRIPT where the take aligned, timing from the AUDIO
  * hard fillers are never captioned; commas and full stops are dropped, ? and ! kept
  * a chunk appears lead_frames (2) before its first word: early reads as snappy, late reads as broken
  * chunks hold at least min_hold (0.4 s) and bridge gaps < 0.3 s so captions don't flicker

edl.captions.overrides  [{"find": "ג'יפיטי", "replace": "GPT"}]  fix words or phrases, timing kept
edl.captions.emphasis   ["חינם"]                                   highlight words as standalone chunks
"""
import re
import sys

from common import Job, is_filler, load, norm_word, save, tokenize
from edl import duration, timeline

STRIP = re.compile(r"[,.;:…\-–—\"״]+$|^[\"״]+")
SENTENCE_END = re.compile(r"[.?!…]$")


def placed_words(job: Job, edl: dict, field: str = "display") -> list[dict]:
    """Words that survive the cut, on the OUTPUT timeline. field='text' gives what was actually heard."""
    analysis = load(job.analysis_path)
    fps = edl["canvas"]["fps"]
    out, spans = [], []
    for s in timeline(edl):
        a, b = s["f_in"] / fps, s["f_out"] / fps
        for w in analysis["words"]:
            if w["asset"] != s["asset"] or w["hard_filler"]:
                continue
            mid = (w["start"] + w["end"]) / 2
            if a <= mid <= b:
                o0 = s["o_start"] + max(0.0, w["start"] - a)
                o1 = s["o_start"] + min(b, w["end"]) - a
                spans.append((w, o0, max(o1, o0 + 0.05), s.get("beat")))
    # a display of "" belongs to the previous word's span (script words replacing several heard ones)
    for k, (w, o0, o1, beat) in enumerate(spans):
        toks = tokenize(w[field])
        if not toks:
            continue
        end = o1
        j = k + 1
        while j < len(spans) and not tokenize(spans[j][0][field]) and spans[j][0]["asset"] == w["asset"]:
            end = spans[j][2]
            j += 1
        n = len(toks)
        for i, t in enumerate(toks):
            out.append({"text": t, "start": round(o0 + (end - o0) * i / n, 4),
                        "end": round(o0 + (end - o0) * (i + 1) / n, 4), "beat": beat})
    return out


def apply_overrides(words: list[dict], overrides: list[dict]) -> list[dict]:
    for ov in overrides or []:
        find = [norm_word(x) for x in tokenize(ov["find"])]
        repl = tokenize(ov.get("replace", ""))
        if not find:
            continue
        i, res = 0, []
        while i < len(words):
            seg = words[i: i + len(find)]
            if len(seg) == len(find) and [norm_word(w["text"]) for w in seg] == find:
                t0, t1 = seg[0]["start"], seg[-1]["end"]
                n = max(1, len(repl))
                for k, r in enumerate(repl):
                    res.append({"text": r, "start": round(t0 + (t1 - t0) * k / n, 4),
                                "end": round(t0 + (t1 - t0) * (k + 1) / n, 4), "beat": seg[0].get("beat")})
                i += len(find)
            else:
                res.append(words[i])
                i += 1
        words = res
    return words


def chunk(words: list[dict], style: dict, emphasis: list[str], fps: int, total: float) -> list[dict]:
    emph = {norm_word(x) for x in emphasis or []}
    chunks, cur = [], []

    def flush():
        if cur:
            chunks.append(list(cur))
            cur.clear()

    for w in words:
        raw = w["text"]
        text = STRIP.sub("", raw).strip() or raw
        item = {"text": text, "start": w["start"], "end": w["end"], "ends_sentence": bool(SENTENCE_END.search(raw)),
                "emphasis": norm_word(text) in emph, "beat": w.get("beat")}
        if item["emphasis"]:
            flush()
            cur.append(item)
            flush()
            continue
        if cur:
            chars = sum(len(x["text"]) for x in cur) + len(cur) + len(text)
            if (len(cur) >= style["max_words"] or chars > style["max_chars"]
                    or w["start"] - cur[-1]["end"] > 0.35 or cur[-1]["ends_sentence"]
                    or item["beat"] != cur[-1]["beat"]):
                flush()
        cur.append(item)
    flush()

    lead = style.get("lead_frames", 2) / fps
    out = []
    for k, c in enumerate(chunks):
        start = max(0.0, c[0]["start"] - lead)
        if out:
            start = max(start, out[-1]["end"])
        nxt = chunks[k + 1][0]["start"] - lead if k + 1 < len(chunks) else total
        end = max(c[-1]["end"], start + style.get("min_hold", 0.4))
        if nxt - end < 0.3:
            end = nxt
        end = min(end, nxt, total)
        if end - start < 1.0 / fps:
            continue
        out.append({"start": round(start, 4), "end": round(end, 4),
                    "text": " ".join(x["text"] for x in c),
                    "emphasis": any(x["emphasis"] for x in c),
                    "words": [{"text": x["text"], "start": x["start"], "end": x["end"]} for x in c]})
    return out


def build_captions(job: Job, edl: dict) -> list[dict]:
    cap = edl["captions"]
    if not cap.get("enabled", True):
        return []
    if cap.get("locked") and cap.get("chunks"):
        return cap["chunks"]
    words = apply_overrides(placed_words(job, edl), cap.get("overrides"))
    return chunk(words, cap["style"], cap.get("emphasis"), edl["canvas"]["fps"], duration(edl))


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    job = Job(sys.argv[1])
    path = job.edit_dir(sys.argv[2]) / "edl.json"
    edl = load(path)
    edl["captions"]["chunks"] = build_captions(job, edl)
    save(path, edl)
    for c in edl["captions"]["chunks"]:
        print(f"  {c['start']:6.2f}–{c['end']:6.2f}  {'*' if c['emphasis'] else ' '} {c['text']}")
    print(f"{len(edl['captions']['chunks'])} chunks -> {path}")


if __name__ == "__main__":
    main()
