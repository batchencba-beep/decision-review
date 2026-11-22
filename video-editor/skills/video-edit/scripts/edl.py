"""The Edit Decision List: format, timeline maths, snapping and validation.

edl.json (all times in SECONDS; source times for segments, output times for cutaways/captions):
{
  "version": "v1",
  "canvas": {"width": 2160, "height": 3840, "fps": 30},
  "segments": [                       # the spoken track, in playback order
    {"id": "s1", "asset": "a1", "in": 12.34, "out": 15.67,
     "beat": 0, "zoom": 1.0, "anchor": [0.5, 0.4], "reason": "hook, take 2 of 2"}
  ],
  "cutaways": [                       # b-roll laid over the spoken track (picture only)
    {"id": "c1", "asset": "a3", "beats": [2],          # either anchor to beats ...
     "at": null, "duration": null,                     # ... or give output time + length
     "src_in": 0.0, "trim_start": 0.0, "trim_end": 0.0, "reason": "..."}
  ],
  "captions": {"enabled": true, "style": {...}, "overrides": [{"find": "...", "replace": "..."}],
               "emphasis": ["word", ...], "locked": false, "chunks": [...generated...]},
  "audio": {"fade_ms": 12},
  "notes": ["..."]
}
"""
from __future__ import annotations

from common import Envelope, Job, load, to_frame

MIN_SEGMENT = 0.20
MAX_ZOOM = 1.5
MIN_EFFECTIVE_WIDTH = 1080  # never let a punch-in drop below what Instagram shows


# ---------------------------------------------------------------- timeline

def frames(seg: dict, fps: int) -> tuple[int, int]:
    return to_frame(seg["in"], fps), to_frame(seg["out"], fps)


def timeline(edl: dict) -> list[dict]:
    """Segments with output start/end (seconds, frame-exact)."""
    fps = edl["canvas"]["fps"]
    t, out = 0, []
    for s in edl["segments"]:
        f0, f1 = frames(s, fps)
        n = f1 - f0
        out.append({**s, "f_in": f0, "f_out": f1, "frames": n, "o_start": t / fps, "o_end": (t + n) / fps,
                    "o_f0": t, "o_f1": t + n})
        t += n
    return out


def duration(edl: dict) -> float:
    tl = timeline(edl)
    return tl[-1]["o_end"] if tl else 0.0


def src_to_out(tl: list[dict], asset: str, t: float, fps: int) -> float | None:
    """Output time of a source instant, or None if that instant was cut."""
    for s in tl:
        a, b = s["f_in"] / fps, s["f_out"] / fps
        if s["asset"] == asset and a - 1e-6 <= t <= b + 1e-6:
            return s["o_start"] + (t - a)
    return None


def beat_spans(tl: list[dict]) -> dict[int, tuple[float, float]]:
    spans = {}
    for s in tl:
        b = s.get("beat")
        if b is None:
            continue
        a, e = spans.get(b, (s["o_start"], s["o_end"]))
        spans[b] = (min(a, s["o_start"]), max(e, s["o_end"]))
    return spans


def resolve_cutaways(edl: dict, probe: dict) -> list[dict]:
    """Cutaways with concrete output at/duration and source in-point."""
    tl = timeline(edl)
    total = duration(edl)
    spans = beat_spans(tl)
    durs = {a["id"]: a["duration"] for a in probe["assets"]}
    out = []
    for c in edl.get("cutaways", []):
        if c.get("at") is not None:
            at = float(c["at"])
            dur = float(c.get("duration") or (durs[c["asset"]] - c.get("src_in", 0)))
        else:
            bs = [spans[b] for b in c.get("beats", []) if b in spans]
            if not bs:
                continue
            at = min(x[0] for x in bs) + float(c.get("trim_start", 0))
            end = max(x[1] for x in bs) - float(c.get("trim_end", 0))
            dur = end - at
        dur = min(dur, durs[c["asset"]] - float(c.get("src_in", 0)), total - at)
        if dur <= 0:
            continue
        out.append({**c, "at": round(at, 4), "duration": round(dur, 4), "src_in": float(c.get("src_in", 0))})
    return out


# ---------------------------------------------------------------- snapping

def words_by_asset(analysis: dict) -> dict[str, list[dict]]:
    res = {}
    for w in analysis["words"]:
        res.setdefault(w["asset"], []).append(w)
    return res


def bounds_for(point: float, words: list[dict], is_in: bool) -> tuple[float, float]:
    """Allowed window for a cut point: the gap it sits in (after moving it out of any word)."""
    for k, w in enumerate(words):
        if w["start"] + 0.01 < point < w["end"] - 0.01:
            # inside a word: include the whole word in the segment
            point = w["start"] - 0.03 if is_in else w["end"] + 0.03
            break
    prev_end = max([w["end"] for w in words if w["end"] <= point + 1e-6], default=0.0)
    next_start = min([w["start"] for w in words if w["start"] >= point - 1e-6], default=1e9)
    return point, prev_end, next_start


def snap_point(point: float, words: list[dict], env: Envelope, fps: int, is_in: bool,
               window: float = 0.04) -> float:
    point, lo, hi = bounds_for(point, words, is_in)
    q = env.quietest(point, window, lo=lo + 0.005, hi=hi - 0.005)
    f = round(q * fps)
    cands = [x for x in (f - 1, f, f + 1) if lo - 1e-6 <= x / fps <= hi + 1e-6]
    if cands:
        f = min(cands, key=lambda x: abs(x / fps - q))
    return round(f / fps, 4)


def snap(job: Job, edl: dict) -> list[str]:
    """Move every segment boundary out of words, into the quietest spot, onto the frame grid."""
    analysis = load(job.analysis_path)
    wba = words_by_asset(analysis)
    fps = edl["canvas"]["fps"]
    envs, changes = {}, []
    for s in edl["segments"]:
        env = envs.setdefault(s["asset"], Envelope(job.wav(s["asset"])))
        ws = wba.get(s["asset"], [])
        for key, is_in in (("in", True), ("out", False)):
            old = s[key]
            new = snap_point(old, ws, env, fps, is_in)
            if abs(new - old) > 0.0005:
                s[key] = new
                if abs(new - old) > 0.5 / fps:
                    changes.append(f"{s['id']}.{key} {old:.3f}→{new:.3f}")
    return changes


# ---------------------------------------------------------------- validation

def validate(job: Job, edl: dict) -> tuple[list[str], list[str]]:
    errors, warns = [], []
    probe = job.probe()
    assets = {a["id"]: a for a in probe["assets"]}
    canvas = edl["canvas"]
    fps = canvas["fps"]
    analysis = load(job.analysis_path) if job.analysis_path.exists() else {"words": []}
    wba = words_by_asset(analysis)
    if not edl.get("segments"):
        errors.append("no segments")
        return errors, warns
    ids = set()
    for s in edl["segments"]:
        sid = s.get("id", "?")
        if sid in ids:
            errors.append(f"duplicate segment id {sid}")
        ids.add(sid)
        a = assets.get(s.get("asset"))
        if not a:
            errors.append(f"{sid}: unknown asset {s.get('asset')}")
            continue
        if a["role"] != "a_roll":
            errors.append(f"{sid}: segments must use a_roll assets (use cutaways for b-roll)")
        if not (0 <= s["in"] < s["out"] <= a["duration"] + 0.05):
            errors.append(f"{sid}: in/out {s['in']}–{s['out']} outside 0–{a['duration']}")
        if s["out"] - s["in"] < MIN_SEGMENT:
            warns.append(f"{sid}: very short segment ({s['out'] - s['in']:.2f}s) reads as a glitch")
        for key in ("in", "out"):
            for w in wba.get(s["asset"], []):
                if w["start"] + 0.015 < s[key] < w["end"] - 0.015:
                    errors.append(f"{sid}.{key}={s[key]:.3f} cuts through the word '{w['text']}' "
                                  f"({w['start']:.2f}–{w['end']:.2f}) — run with --snap")
        z = float(s.get("zoom", 1.0))
        if z > 1.0 and not job.brief["style"]["zoom"]:
            errors.append(f"{sid}: zoom {z} — the brief says no zooms (movement comes from the speaker). "
                          f"Hide jump cuts with a cutaway or a better cut point instead")
        if z < 1.0 or z > MAX_ZOOM:
            errors.append(f"{sid}: zoom {z} outside 1.0–{MAX_ZOOM}")
        if z > 1.0:
            cover = max(canvas["width"] / a["width"], canvas["height"] / a["height"])
            visible = canvas["width"] / (cover * z)  # source pixels across the frame after the punch-in
            if visible < MIN_EFFECTIVE_WIDTH:
                errors.append(f"{sid}: zoom {z} leaves {visible:.0f} source px across the frame — "
                              f"below {MIN_EFFECTIVE_WIDTH}px it looks soft (max zoom here "
                              f"{canvas['width'] / cover / MIN_EFFECTIVE_WIDTH:.2f})")
    tl = timeline(edl)
    total = tl[-1]["o_end"]
    for c in resolve_cutaways(edl, probe):
        a = assets.get(c["asset"])
        if not a:
            errors.append(f"{c.get('id')}: unknown asset {c['asset']}")
            continue
        if c["at"] < 0 or c["at"] + c["duration"] > total + 0.05:
            errors.append(f"{c.get('id')}: cutaway {c['at']:.2f}+{c['duration']:.2f}s outside timeline {total:.2f}s")
        if c["duration"] < 0.5:
            warns.append(f"{c.get('id')}: cutaway shorter than 0.5s flashes by")
        cover = max(canvas["width"] / a["width"], canvas["height"] / a["height"])
        if cover > 2.0:
            errors.append(f"{c.get('id')}: {a['width']}x{a['height']} needs {cover:.1f}x upscale (max 2x)")
        elif cover > 1.01:
            warns.append(f"{c.get('id')}: {a['id']} upscaled {cover:.2f}x (lanczos) — slightly softer than A-roll")
    # framing jumps: consecutive segments from different camera setups with no cutaway over the join
    sp = job.work / "setups.json"
    if sp.exists():
        from setups import setup_of_span
        sdata = load(sp)
        cuts_covered = [(c["at"], c["at"] + c["duration"]) for c in resolve_cutaways(edl, probe)]
        prev = None
        for s in tl:
            cur = setup_of_span(sdata, s["asset"], s["f_in"] / fps, s["f_out"] / fps)
            if prev and cur and prev[1] != cur and not any(a - 0.05 <= s["o_start"] <= b + 0.05 for a, b in cuts_covered):
                msg = (f"{s['id']}: camera setup changes {prev[1]}→{cur} at {s['o_start']:.2f}s with nothing "
                       f"covering the cut — the speaker jumps position")
                (errors if job.brief["style"]["continuity"] == "single" and not s.get("allow_setup_switch")
                 else warns).append(msg + ("; cover it with a cutaway, use a take from the same setup, or set "
                                           "allow_setup_switch on the segment if it is deliberate"
                                           if job.brief["style"]["continuity"] == "single" else ""))
            prev = (s["id"], cur)

    target = job.brief["target"]["max_seconds"]
    if total > target + 0.5:
        warns.append(f"duration {total:.1f}s is over the {target:.0f}s target — cut the weakest beat")
    first = tl[0]
    ws = [w for w in wba.get(first["asset"], []) if first["in"] <= w["start"] < first["out"]]
    if ws and ws[0]["start"] - first["in"] > 0.3:
        warns.append(f"first word lands at {ws[0]['start'] - first['in']:.2f}s — should be ≤ 0.30s")
    spans = beat_spans(tl)
    hook = next((b for b in analysis.get("beats", []) if b["kind"] == "hook"), None)
    hb = hook.get("beat", hook["index"]) if hook else None
    if hook and hb in spans and spans[hb][1] > 3.0:
        warns.append(f"hook ends at {spans[hb][1]:.2f}s — must land by 3.0s")
    return errors, warns
