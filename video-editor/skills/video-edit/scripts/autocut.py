#!/usr/bin/env python3
"""Step 5 — a mechanical first cut, written as an EDL for the editor to judge and revise.

usage: autocut.py <job> [--version v1] [--gap 0.30] [--pad 0.10] [--keep-fillers]

Rules applied (each cut gets a "reason"):
  * script order; for each beat the chosen take from analysis.json (★)
  * off-script speech, false starts and unused takes are dropped
  * pauses longer than --gap (default 0.30 s) are closed, leaving --pad breathing room each side
  * hard fillers (אממ, אה, um, uh ...) are removed; soft ones (כאילו, בעצם, like) are left to the editor
  * gaps with unworded SOUND are only tightened, never removed blind — they may hide a missed word
  * every boundary is snapped out of words, into the quietest 5 ms, onto the 30 fps frame grid
  * b_roll assets with beat_ref become cutaways anchored to those beats

This is a starting point. The agent then reads the EDL against analysis.json and the brief, and makes
the editorial calls a rule cannot: which take really is better, which beat to drop for length, which
soft filler matters.
"""
import argparse

from common import Envelope, Job, load, save, tc
from edl import duration, snap, timeline, validate

CAPTION_PRESETS = {
    # loud reels look: big, outlined, coloured active word, pop-in
    "bold": {"max_words": 3, "max_chars": 16, "position_y": 0.64, "font_weight": 800, "size": 0.074,
             "lead_frames": 2, "min_hold": 0.40, "animation": "pop", "highlight_mode": "color",
             "shadow": "strong"},
    # quiet, designed look: smaller, no outline, soft shadow, the active word lifts by opacity, fade-in
    "quiet": {"max_words": 4, "max_chars": 22, "position_y": 0.70, "font_weight": 500, "size": 0.052,
              "lead_frames": 2, "min_hold": 0.50, "animation": "fade", "highlight_mode": "opacity",
              "shadow": "soft"},
}


def groups_for_take(take_words: list[dict], gap_max: float, keep_fillers: bool, gaps_by_after: dict):
    """Split a take into runs of kept words."""
    runs, cur, reasons = [], [], []
    for k, w in enumerate(take_words):
        if w["hard_filler"] and not keep_fillers:
            if cur:
                runs.append(cur)
            cur = []
            reasons.append(f"filler '{w['text']}' {tc(w['start'])}")
            continue
        if cur:
            gap = w["start"] - cur[-1]["end"]
            g = gaps_by_after.get((w["asset"], cur[-1]["i"]))
            sound = g is not None and g["kind"] == "sound"
            if gap > gap_max and not sound:
                runs.append(cur)
                cur = []
                reasons.append(f"pause {gap:.2f}s {tc(w['start'])}")
            elif gap > 0.8 and sound:
                reasons.append(f"kept {gap:.2f}s gap with sound at {tc(w['start'])} — check it")
        cur.append(w)
    if cur:
        runs.append(cur)
    return runs, reasons


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job")
    ap.add_argument("--version")
    ap.add_argument("--gap", type=float, default=0.30)
    ap.add_argument("--pad", type=float, default=0.10)
    ap.add_argument("--keep-fillers", action="store_true")
    opt = ap.parse_args()

    job = Job(opt.job)
    analysis = load(job.analysis_path)
    canvas = job.canvas()
    words = analysis["words"]
    by_asset = {}
    for w in words:
        by_asset.setdefault(w["asset"], []).append(w)
    gaps_by_after = {(g["asset"], g["after_word"]): g for g in analysis["gaps"]}
    envs = {a: Envelope(job.wav(a)) for a in by_asset}

    segments, notes = [], []
    for b in analysis["beats"]:
        take = next((t for t in b["takes"] if t["chosen"]), None)
        if take is None:
            if b["kind"] == "aside":
                continue
            notes.append(f"beat {b.get('beat', b['index'])} ({b['kind']}: {b['text'][:40]}) has no take in the footage — missing from the edit")
            continue
        others = len(b["takes"]) - 1
        tw = [w for w in words if take["w0"] <= w["g"] <= take["w1"]]
        runs, reasons = groups_for_take(tw, opt.gap, opt.keep_fillers, gaps_by_after)
        aw = by_asset[take["asset"]]
        for r_i, run in enumerate(runs):
            first, last = run[0], run[-1]
            pre = 0.06 if not segments else opt.pad
            prev_w = next((w for w in reversed(aw) if w["end"] <= first["start"] - 1e-6), None)
            next_w = next((w for w in aw if w["start"] >= last["end"] + 1e-6), None)
            lo = prev_w["end"] + 0.01 if prev_w else 0.0
            hi = next_w["start"] - 0.01 if next_w else envs[take["asset"]].duration
            seg_in = max(lo, first["start"] - pre)
            seg_out = min(hi, last["end"] + opt.pad)
            why = f"{b['kind']} {b['index']}, take {b['takes'].index(take) + 1} of {others + 1}"
            if take.get("setup"):
                why += f", setup {take['setup']}" + (" (SWITCH — will jump)" if b.get("setup_switch") else "")
            if r_i == 0 and reasons:
                why += "; " + "; ".join(reasons)
            segments.append({"asset": take["asset"], "setup": take.get("setup"), "in": round(seg_in, 4), "out": round(seg_out, 4),
                             "beat": b.get("beat", b["index"]), "zoom": 1.0, "anchor": [0.5, 0.4], "reason": why})

    for n in analysis.get("continuity", {}).get("notes", []):
        notes.append(n)
    off = [b for b in analysis["beats"] if b["kind"] == "off_point"]
    for b in off:
        notes.append(f"kept off-point sentence '{b['text'][:50]}' — matches no talking point; cut it unless it earns its place")

    # merge runs that ended up touching
    merged = []
    for s in segments:
        if merged and merged[-1]["asset"] == s["asset"] and merged[-1]["beat"] == s["beat"] \
                and s["in"] - merged[-1]["out"] < 0.02:
            merged[-1]["out"] = s["out"]
        else:
            merged.append(s)
    for k, s in enumerate(merged):
        s["id"] = f"s{k + 1}"

    cutaways = []
    for a in job.brief["assets"]:
        if a["role"] == "b_roll" and a["beat_ref"]:
            cutaways.append({"id": f"c{len(cutaways) + 1}", "asset": a["id"], "beats": list(a["beat_ref"]),
                             "at": None, "duration": None, "src_in": 0.0, "trim_start": 0.0, "trim_end": 0.0,
                             "reason": f"brief maps {a['id']} to beats {a['beat_ref']}"})
        elif a["role"] == "b_roll":
            notes.append(f"{a['id']} ({a['type']}) has no beat_ref — place it by hand or leave it out")

    brand = job.brief["brand"]
    preset = job.brief["style"]["captions"]
    style = dict(CAPTION_PRESETS.get(preset, CAPTION_PRESETS["bold"]))
    style.update({"font": brand["caption_font"], "color": brand["primary"], "highlight": brand["highlight"],
                  "stroke": "none" if preset == "quiet" else brand["stroke"]})
    if brand.get("font_file"):
        style["font_file"] = brand["font_file"]
    edl = {
        "version": opt.version or job.next_version(),
        "brief_id": job.brief["id"],
        "canvas": canvas,
        "segments": merged,
        "cutaways": cutaways,
        "captions": {"enabled": preset != "none", "preset": preset, "language": job.brief["target"]["language"],
                     "style": style,
                     "overrides": [], "emphasis": [], "locked": False, "chunks": []},
        "audio": {"fade_ms": 12},
        "notes": notes,
    }
    changes = snap(job, edl)
    errors, warns = validate(job, edl)
    edl["notes"] += warns
    out = job.edit_dir(edl["version"]) / "edl.json"
    save(out, edl)

    tl = timeline(edl)
    print(f"{edl['version']}: {len(merged)} segments, {len(cutaways)} cutaways, {duration(edl):.2f}s")
    for s in tl:
        print(f"  {s['id']:<4} {s['asset']} {tc(s['in'])}–{tc(s['out'])} -> out {tc(s['o_start'])} | {s['reason']}")
    for n in edl["notes"]:
        print(f"  note: {n}")
    for e in errors:
        print(f"  ERROR: {e}")
    if changes:
        print(f"  snapped {len(changes)} boundaries off words / onto quiet frames")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
