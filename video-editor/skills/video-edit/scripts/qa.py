#!/usr/bin/env python3
"""Self-QA on a rendered draft. Nothing goes to the user before this passes.

usage: qa.py <job> <version> [--no-transcribe]

Machine checks (qa/report.json):
  format     resolution, 30/1 constant frame rate, yuv420p, Rec.709 tags, AAC 48 kHz, duration = EDL
  loudness   integrated -14 LUFS ±1, true peak ≤ -1 dBTP (EBU R128 scan of each export)
  picture    black frames, frozen picture, on the master
  words      re-transcribes the EXPORT and diffs it against the words the EDL intended:
             a word missing next to a cut = clipped at the cut; extra words = a cut that let something in
  sync       caption timing vs the re-transcribed audio (median and worst offset)
  layout     caption chunks that will not fit on one line in the safe zone

Frames for the agent to LOOK at (Read the images — that is the visual check):
  qa/contact_sheet.jpg     the first frame after every cut, in order (cut flashes, jump-cut jolts, framing)
  qa/cuts/cut_XX.jpg       last frame before | first frame after each cut, side by side
  qa/captions/cap_XX.jpg   caption chunks over picture (legibility, safe zone, RTL order, overlap with face)
"""
import statistics
import sys
from difflib import SequenceMatcher

from common import Job, ffmpeg, ffprobe_json, load, norm_word, run, save, to_frame
from edl import duration, resolve_cutaways, timeline

MAX_CAPTION_FRAMES = 14


def probe_export(path, edl) -> list[str]:
    errs = []
    info = ffprobe_json(path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fps = edl["canvas"]["fps"]
    if v["r_frame_rate"] != f"{fps}/1" or v["avg_frame_rate"] != f"{fps}/1":
        errs.append(f"frame rate r={v['r_frame_rate']} avg={v['avg_frame_rate']} (want {fps}/1 CFR)")
    if v.get("pix_fmt") != "yuv420p":
        errs.append(f"pix_fmt {v.get('pix_fmt')}")
    for k in ("color_primaries", "color_transfer", "color_space"):
        if v.get(k) != "bt709":
            errs.append(f"{k}={v.get(k)} (want bt709)")
    if not a or a.get("codec_name") != "aac" or a.get("sample_rate") != "48000":
        errs.append("audio is not AAC 48 kHz")
    want = duration(edl)
    got = float(info["format"]["duration"])
    if abs(got - want) > 2.5 / fps:
        errs.append(f"duration {got:.3f}s vs EDL {want:.3f}s")
    return errs, {"width": v["width"], "height": v["height"], "duration": round(got, 3)}


def loudness(path) -> dict:
    p = run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-af", "ebur128=peak=true",
             "-f", "null", "-"], capture=True)
    tail = p.stderr[p.stderr.rfind("Summary:"):]
    vals = {}
    for line in tail.splitlines():
        line = line.strip()
        if line.startswith("I:"):
            vals["integrated"] = float(line.split()[1])
        elif line.startswith("Peak:"):
            vals["true_peak"] = float(line.split()[1])
    return vals


def detect(master) -> dict:
    p = run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(master), "-an", "-vf",
             "blackdetect=d=0.05:pix_th=0.06,freezedetect=n=-55dB:d=1.2", "-f", "null", "-"], capture=True)
    black = [l.split("black_start:")[1].split()[0] for l in p.stderr.splitlines() if "black_start:" in l]
    freeze = [l.split("freeze_start:")[1].split()[0] for l in p.stderr.splitlines() if "freeze_start:" in l]
    return {"black_at": [float(x) for x in black], "frozen_at": [float(x) for x in freeze]}


def grab(src, frames: list[int], pattern, width: int):
    """Extract specific frame numbers in one decode pass."""
    if not frames:
        return
    expr = "+".join(f"eq(n\\,{f})" for f in sorted(set(frames)))
    pattern.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg(["-i", str(src), "-an", "-vf", f"select='{expr}',scale={width}:-2:flags=lanczos",
            "-fps_mode", "passthrough", "-q:v", "3", "-start_number", "0", str(pattern)])


def visual_frames(d, edl, master, probe):
    fps = edl["canvas"]["fps"]
    tl = timeline(edl)
    total = tl[-1]["o_f1"]
    qa = d / "qa"
    for sub in ("cuts", "captions", "_tmp"):
        (qa / sub).mkdir(parents=True, exist_ok=True)
        for f in (qa / sub).glob("*.jpg"):
            f.unlink()
    # cut points: output frames where the picture changes (segment joins + cutaway in/out)
    cuts = [s["o_f0"] for s in tl[1:]]
    for c in resolve_cutaways(edl, probe):
        cuts += [to_frame(c["at"], fps), to_frame(c["at"] + c["duration"], fps)]
    cuts = sorted({c for c in cuts if 0 < c < total})
    pairs = []
    for c in cuts:
        pairs += [c - 1, c]
    grab(master, pairs, qa / "_tmp" / "p_%04d.jpg", 360)
    tmp = sorted((qa / "_tmp").glob("p_*.jpg"))
    frame_of = sorted(set(pairs))
    img = {f: p for f, p in zip(frame_of, tmp)}
    after = []
    for k, c in enumerate(cuts):
        if c - 1 in img and c in img:
            out = qa / "cuts" / f"cut_{k + 1:02d}.jpg"
            ffmpeg(["-i", str(img[c - 1]), "-i", str(img[c]), "-filter_complex",
                    "[0][1]hstack=inputs=2", "-q:v", "3", str(out)])
            after.append(img[c])
    sheet = None
    if after:
        cols = min(6, len(after))
        rows = (len(after) + cols - 1) // cols
        lst = qa / "_tmp" / "sheet.txt"
        lst.write_text("".join(f"file '{p}'\nduration 1\n" for p in after))
        sheet = qa / "contact_sheet.jpg"
        ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-vf",
                f"scale=240:-2,tile={cols}x{rows}:padding=6:color=white", "-frames:v", "1", "-q:v", "3", str(sheet)])
    # caption frames: middle of chunks, spread across the reel
    chunks = edl["captions"].get("chunks", [])
    pick = chunks if len(chunks) <= MAX_CAPTION_FRAMES else \
        [chunks[round(i * (len(chunks) - 1) / (MAX_CAPTION_FRAMES - 1))] for i in range(MAX_CAPTION_FRAMES)]
    cap_frames = [min(total - 1, to_frame((c["start"] + c["end"]) / 2, fps)) for c in pick]
    grab(master, cap_frames, qa / "captions" / "cap_%02d.jpg", 540)
    for f in (qa / "_tmp").glob("*"):
        f.unlink()
    (qa / "_tmp").rmdir()
    return {"cuts": len(cuts), "contact_sheet": str(sheet) if sheet else None,
            "caption_frames": len(cap_frames), "cut_frames_at": cuts}



def word_check(job, d, edl, export_path) -> dict:
    from transcribe import transcribe_wav
    wav = d / "qa" / "export_16k.wav"
    ffmpeg(["-i", str(export_path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
    got = transcribe_wav(wav, job.brief["target"]["language"])["words"]
    wav.unlink()
    from captions import placed_words
    # compare HEARD against HEARD: the transcript of the kept words, not the script-spelled captions
    # (otherwise "ארבעה אחוזים" in the captions vs "4%" in the audio looks like a missing word)
    want = placed_words(job, edl, field="text")
    if not want:
        return {"skipped": "no words to compare"}
    wk, gk = [norm_word(w["text"]) for w in want], [norm_word(w["text"]) for w in got]
    cut_times = [s["o_start"] for s in timeline(edl)[1:]]
    missing, extra, offsets = [], [], []
    for op, a0, a1, b0, b1 in SequenceMatcher(None, wk, gk, autojunk=False).get_opcodes():
        if op == "equal":
            offsets += [got[b0 + k]["start"] - want[a0 + k]["start"] for k in range(a1 - a0)]
        if op in ("delete", "replace"):
            for w in want[a0:a1]:
                near = min((abs(w["start"] - c) for c in cut_times), default=99) < 0.35 or \
                       min((abs(w["end"] - c) for c in cut_times), default=99) < 0.35
                missing.append({"text": w["text"], "at": round(w["start"], 2), "near_cut": near})
        if op in ("insert", "replace"):
            extra += [{"text": w["text"], "at": round(w["start"], 2)} for w in got[b0:b1]]
    ratio = SequenceMatcher(None, wk, gk, autojunk=False).ratio()
    sync = {}
    if offsets:
        sync = {"median_ms": round(1000 * statistics.median(offsets)),
                "worst_ms": round(1000 * max(offsets, key=abs)),
                "within_100ms": round(sum(abs(o) <= 0.1 for o in offsets) / len(offsets), 2)}
    return {"match_ratio": round(ratio, 3), "missing": missing, "extra": extra, "sync": sync}


def layout_check(edl) -> list[str]:
    st = edl["captions"]["style"]
    W = edl["canvas"]["width"]
    safe_w = W * (1 - 0.06 - 0.16)
    font_px = st.get("size", 0.074) * W
    warns = []
    for c in edl["captions"].get("chunks", []):
        est = len(c["text"]) * font_px * 0.56 * (1.22 if c.get("emphasis") else 1)
        if est > safe_w:
            warns.append(f"'{c['text']}' at {c['start']:.2f}s may wrap to two lines")
    return warns


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(args) != 2:
        raise SystemExit(__doc__)
    job = Job(args[0])
    d = job.edit_dir(args[1])
    edl = load(d / "edl.json")
    master = d / "master.mov"
    exports = sorted((d / "exports").glob("*.mp4"))
    problems, warnings = [], []
    report = {"version": args[1], "duration": round(duration(edl), 3), "exports": {}}

    for e in exports:
        errs, meta = probe_export(e, edl)
        lo = loudness(e)
        if abs(lo.get("integrated", 0) - (-14)) > 1.0:
            errs.append(f"loudness {lo.get('integrated')} LUFS (want -14 ±1)")
        if lo.get("true_peak", 0) > -0.9:
            errs.append(f"true peak {lo.get('true_peak')} dBTP (want ≤ -1)")
        report["exports"][e.name] = {**meta, "loudness": lo, "errors": errs}
        problems += [f"{e.name}: {x}" for x in errs]

    det = detect(master)
    report["picture"] = det
    if det["black_at"]:
        problems.append(f"black frames at {det['black_at']}")
    if det["frozen_at"]:
        warnings.append(f"picture frozen ≥1.2s at {det['frozen_at']} — check it is intentional")

    report["frames"] = visual_frames(d, edl, master, job.probe())
    report["layout"] = layout_check(edl)
    warnings += report["layout"]

    if "--no-transcribe" not in sys.argv and exports:
        wc = word_check(job, d, edl, exports[0])
        report["words"] = wc
        for m in wc.get("missing", []):
            (problems if m["near_cut"] else warnings).append(
                f"word '{m['text']}' at {m['at']}s not heard in export" + (" — clipped at a cut?" if m["near_cut"] else ""))
        if wc.get("extra"):
            warnings.append("heard but not captioned: " + ", ".join(f"'{x['text']}'@{x['at']}" for x in wc["extra"][:8]))
        s = wc.get("sync") or {}
        if s and (abs(s["median_ms"]) > 80 or s["within_100ms"] < 0.8):
            warnings.append(f"caption sync median {s['median_ms']} ms, worst {s['worst_ms']} ms, "
                            f"{int(100 * s['within_100ms'])}% within 100 ms")

    for n in edl.get("notes", []):
        warnings.append(f"edl note: {n}")
    report["problems"], report["warnings"] = problems, warnings
    report["status"] = "fail" if problems else "pass"
    save(d / "qa" / "report.json", report)

    print(f"QA {args[1]}: {report['status'].upper()}  ({report['duration']:.2f}s, {report['frames']['cuts']} cuts)")
    for k, v in report["exports"].items():
        print(f"  {k}: {v['width']}x{v['height']} {v['duration']}s  {v['loudness']}")
    if "words" in report and "match_ratio" in report["words"]:
        print(f"  words: {report['words']['match_ratio']:.0%} of intended words heard; sync {report['words']['sync']}")
    for p in problems:
        print(f"  PROBLEM: {p}")
    for w in warnings:
        print(f"  warn: {w}")
    print(f"  look at: {report['frames']['contact_sheet']}, {d / 'qa' / 'cuts'}, {d / 'qa' / 'captions'}")


if __name__ == "__main__":
    main()
