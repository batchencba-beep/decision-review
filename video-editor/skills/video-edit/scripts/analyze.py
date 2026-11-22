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
from setups import detect as detect_setups, setup_of_span

MIN_SCORE = 0.55          # below this a span is not considered a take of the beat
PREFER_LATER_WITHIN = 0.06  # editors' rule: the last good take is usually the keeper
GAP_MIN = 0.25


def setups_for(job: Job) -> dict | None:
    """Camera setups from the picture (cached in work/setups.json)."""
    path = job.work / "setups.json"
    mezz = [job.mezz(a["id"]) for a in job.a_roll() if job.mezz(a["id"]).exists()]
    if not mezz:
        return None
    if path.exists() and all(path.stat().st_mtime > m.stat().st_mtime for m in mezz):
        return load(path)
    return detect_setups(job)


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


STOP = {norm_word(x) for x in "את של על עם זה זו זאת הוא היא אני אתם אתן הם הן אנחנו לא כן גם רק כל מה מי אז כי אם או אבל יש אין היה הייתה להיות עוד כבר מאוד ממש פשוט the a an to of and or is are it this that".split()}


def utterances(words: list[dict], pause: float = 0.6) -> list[list[dict]]:
    """Split speech into sentences: at sentence punctuation or a pause > 0.6 s."""
    res, cur = [], []
    for w in words:
        if cur and (w["asset"] != cur[-1]["asset"] or w["start"] - cur[-1]["end"] > pause):
            res.append(cur)
            cur = []
        cur.append(w)
        if w["text"].endswith(SENT_END):
            res.append(cur)
            cur = []
    if cur:
        res.append(cur)
    return res


def content(keys: list[str]) -> set[str]:
    return {k for k in keys if k and k not in STOP and len(k) > 1}


def points_beats(words: list[dict], points: list[dict]) -> tuple[list[dict], set[int]]:
    """Free speech around talking points (no word-for-word script).

    Takes are found by REPETITION, not by matching a script: a sentence said again later (similar
    words — anywhere later, so a whole second run-through counts) or restarted within the next three
    sentences is an alternative take of the same line. By default the later one is kept (the speaker
    repeats because the first try was worse); apply_continuity() may then prefer a take from the
    reel's single camera setup. Each kept sentence is tagged with the talking point it covers (content-word overlap),
    which anchors cutaways and tells you which point is missing.
    """
    utts = utterances(words)
    keys = [[w["key"] for w in u] for u in utts]
    superseded = {}
    for i in range(len(utts)):
        for j in range(i + 1, len(utts)):
            sim = SequenceMatcher(None, keys[i], keys[j], autojunk=False).ratio()
            # a partial try: (almost) every word of the earlier sentence reappears, in order, in the
            # later one — a restart ("היום הוא היום הכי שמח" ... "היום הוא היום הכי שמח בחיים שלי")
            # or a fragment Whisper split off ("בחיים שלי.")
            matched = sum(b.size for b in SequenceMatcher(None, keys[i], keys[j], autojunk=False).get_matching_blocks())
            partial = (j <= i + 3 and len(keys[i]) >= 2 and len(keys[i]) <= len(keys[j])
                       and matched / len(keys[i]) >= 0.8)
            if sim >= 0.6 or partial:
                superseded[i] = j
                break
    pkeys = [content([norm_word(x) for x in tokenize(p["text"])]) for p in points]
    out, used = [], set()
    for i, u in enumerate(utts):
        if i in superseded:
            continue
        ck = content(keys[i])
        overlaps = [len(ck & pk) / max(1, min(len(ck), len(pk))) for pk in pkeys]
        best = max(range(len(points)), key=lambda k: overlaps[k]) if points else None
        point = best if best is not None and overlaps[best] >= 0.2 else None
        aside = point is None and len(u) <= 3 and bool(points)
        # all earlier takes of this sentence (follow the supersede chain backwards)
        chain, k = [], i
        while True:
            prev = [a for a, b in superseded.items() if b == k]
            if not prev:
                break
            k = prev[0]
            chain.insert(0, k)
        takes = []
        for n, t_i in enumerate(chain + [i]):
            tu = utts[t_i]
            t = describe_take({"w0": tu[0]["g"], "w1": tu[-1]["g"], "score": 1.0}, words)
            t["chosen"] = (t_i == i) and not aside
            takes.append(t)
        kind = "aside" if aside else ("hook" if point == 0 and points and points[0]["kind"] == "hook" else
                                     "cta" if point is not None and points[point]["kind"] == "cta" else
                                     "off_point" if point is None and points else "sentence")
        out.append({"index": len(out), "kind": kind, "beat": point,
                    "text": " ".join(w["text"] for w in u), "takes": takes})
    covered = {b["beat"] for b in out if b["beat"] is not None and b["kind"] != "aside"}
    for k, p in enumerate(points):
        if k not in covered:
            out.append({"index": len(out), "kind": "missing_point", "beat": k, "text": p["text"], "takes": []})
    return out, used


def apply_continuity(beats: list[dict], sdata: dict | None, policy: str) -> dict:
    """Build the reel from ONE camera setup.

    Picking the best take of every line independently mixes setups, and the speaker jumps position or
    framing on every sentence — the most common amateur-edit look. With policy "single" (default) the
    setup that covers the most lines (then the best takes) is chosen, and every line uses its best take
    from that setup. A line that exists only in another setup keeps that take and is reported: it will
    jump, so cover it with a cutaway or drop it. Policy "free" keeps the best take per line.
    """
    res = {"policy": policy, "setup": None, "notes": [], "setups": (sdata or {}).get("setups", {})}
    for b in beats:
        for t in b["takes"]:
            t["setup"] = setup_of_span(sdata, t["asset"], t["start"], t["end"]) if sdata else None
    names = list(res["setups"])
    live = [b for b in beats if b["takes"] and b["kind"] not in ("aside", "missing_point")]
    if policy == "free" or len(names) <= 1 or not live:
        res["setup"] = names[0] if len(names) == 1 else None
        return res

    def quality(t):
        return t["score"] - 0.02 * t["pauses"] - 0.01 * t["fillers"]

    def rank(sname):
        cov = [b for b in live if any(t["setup"] == sname for t in b["takes"])]
        q = sum(max(quality(t) for t in b["takes"] if t["setup"] == sname) for b in cov)
        return (len(cov), q)

    best = max(names, key=rank)
    res["setup"] = best
    for b in live:
        idx = [n for n, t in enumerate(b["takes"]) if t["setup"] == best]
        if idx:
            sub = pick([b["takes"][n] for n in idx])
            chosen = idx[sub]
        else:
            chosen = next((n for n, t in enumerate(b["takes"]) if t["chosen"]), len(b["takes"]) - 1)
            b["setup_switch"] = True
            res["notes"].append(f"'{b['text'][:45]}' exists only in setup {b['takes'][chosen]['setup']} — "
                                f"the cut into it will jump; cover it with a cutaway or drop the line")
        for n, t in enumerate(b["takes"]):
            t["chosen"] = n == chosen
    return res


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    job = Job(sys.argv[1])
    words = stream(job)
    if not words:
        raise SystemExit("no words transcribed — check the a_roll audio")
    beats = script_beats(job.brief)
    mode = job.brief["script"]["mode"] if beats else "points"
    scripted = mode == "verbatim"

    out_beats, display, used = [], {}, set()
    used_elsewhere: set[int] = set()
    if not scripted:
        out_beats, _ = points_beats(words, beats)
        beats = []
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
            used_elsewhere.update(range(t["w0"], t["w1"] + 1))
        out_beats.append({**{x: b[x] for x in ("index", "kind", "text")}, "beat": b["index"], "takes": takes,
                          "_toks": toks})

    sdata = setups_for(job)
    continuity = apply_continuity(out_beats, sdata, job.brief["style"]["continuity"])
    if not scripted:
        # free speech: play lines in the order they were spoken in the takes actually used
        order = {a["id"]: n for n, a in enumerate(job.a_roll())}

        def when(b):
            t = next((t for t in b["takes"] if t["chosen"]), None)
            return (0, order[t["asset"]], t["start"]) if t else (1, 0, b["index"])
        out_beats.sort(key=when)
        for n, b in enumerate(out_beats):
            b["index"] = n
    for b in out_beats:
        t = next((t for t in b["takes"] if t["chosen"]), None)
        if t is None:
            continue
        used.update(range(t["w0"], t["w1"] + 1))
        if scripted and "_toks" in b:
            display.update(display_text(b["_toks"], words[t["w0"]: t["w1"] + 1]))
    for b in out_beats:
        b.pop("_toks", None)

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
        "mode": mode,
        "continuity": continuity,
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

    c = continuity
    if len(c["setups"]) > 1:
        listing = ", ".join(f"{k} ({v['seconds']}s)" for k, v in c["setups"].items())
        print(f"camera setups: {listing} — "
              f"policy {c['policy']}" + (f", reel uses setup {c['setup']}" if c["setup"] else ""))
        for n in c["notes"]:
            print(f"  !! {n}")
    print(f"mode: {mode}" + ("" if scripted else " — takes found by repetition; sentences tagged with the talking point (p#)"))
    for b in out_beats:
        tag = f" p{b['beat']}" if b.get("beat") is not None and not scripted else ""
        print(f"[{b['index']}] {b['kind']}{tag}: {b['text'][:70]}")
        if not b["takes"]:
            print("     !! NO TAKE FOUND — " + ("talking point not covered in the footage" if not scripted
                                               else "line missing from footage or badly misrecognised"))
        for t in b["takes"]:
            mark = "★" if t["chosen"] else " "
            print(f"   {mark} {t['asset']}{('/' + t['setup']) if t.get('setup') else ''} {tc(t['start'])}–{tc(t['end'])} score={t['score']:.2f} "
                  f"pauses={t['pauses']} fillers={t['fillers']} prob={t['prob']:.2f} | {t['text'][:60]}")
    if data["unmatched"]:
        print("not used (off-script, discarded takes or asides — dropped unless you keep them):")
        for u in data["unmatched"]:
            print(f"   {u['asset']} {tc(u['start'])}–{tc(u['end'])}: {u['text'][:80]}")
    snd = [g for g in data["gaps"] if g["kind"] == "sound"]
    print(f"gaps: {len(data['gaps'])} ({len(snd)} with unworded sound — breath, laugh or a missed word)")
    print(f"-> {job.analysis_path}")


if __name__ == "__main__":
    main()
