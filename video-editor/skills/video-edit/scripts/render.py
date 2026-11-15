#!/usr/bin/env python3
"""Graphics + composite: caption layer in Remotion, everything else in FFmpeg.

usage: render.py <job> <version>          (build.py calls this)

1. captions.mov  Remotion renders ONLY the caption layer, transparent (ProRes 4444 + alpha), at canvas
                 size. Source pixels never pass through the browser — no colour shift, no softening.
2. master.mov    FFmpeg: base.mov + cutaways (cover-fit from their mezzanines) + caption layer
                 -> ProRes 422 HQ master. This is the archive file; exports are made from it.

Env: REMOTION_BROWSER  path to a Chrome/Chromium binary (auto-detected; otherwise Remotion downloads one)
     REMOTION_CONCURRENCY  parallel browser tabs (default: CPU count)
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from common import SKILL_DIR, Job, ffmpeg, load, save, to_frame
from cut import fit_filter
from edl import duration, resolve_cutaways

REMOTION = SKILL_DIR / "remotion"
BROWSERS = ["/opt/pw-browsers/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]


def caption_props(edl: dict, fps: int, total_frames: int) -> dict:
    cap = edl["captions"]
    st = cap["style"]
    chunks = []
    for c in cap.get("chunks", []):
        f0, f1 = to_frame(c["start"], fps), min(total_frames, to_frame(c["end"], fps))
        if f1 <= f0:
            continue
        chunks.append({"from": f0, "to": f1, "emphasis": bool(c.get("emphasis")),
                       "words": [{"text": w["text"], "from": to_frame(w["start"], fps), "to": to_frame(w["end"], fps)}
                                 for w in c["words"]]})
    lang = cap.get("language", "he")
    style = {"font": st.get("font", "Heebo"), "weight": int(st.get("font_weight", 800)),
             "size": float(st.get("size", 0.074)), "color": st.get("color", "#FFFFFF"),
             "highlight": st.get("highlight", "#FFD60A"), "stroke": st.get("stroke", "#000000"),
             "positionY": float(st.get("position_y", 0.64)), "animation": st.get("animation", "pop")}
    if st.get("font_file"):
        style["fontFile"] = Path(st["font_file"]).name
    return {"width": edl["canvas"]["width"], "height": edl["canvas"]["height"], "fps": fps,
            "durationInFrames": total_frames, "direction": "rtl" if lang in ("he", "ar", "yi", "fa") else "ltr",
            "style": style, "chunks": chunks}


def render_captions(job: Job, d: Path, edl: dict, total_frames: int) -> Path | None:
    props = caption_props(edl, edl["canvas"]["fps"], total_frames)
    if not props["chunks"]:
        return None
    if not (REMOTION / "node_modules").exists():
        raise SystemExit(f"Remotion not installed — run scripts/setup.sh (missing {REMOTION / 'node_modules'})")
    props_path = save(d / "captions.props.json", props)
    public = d / "public"
    public.mkdir(exist_ok=True)
    ff = edl["captions"]["style"].get("font_file")
    if ff:
        src = Path(ff) if Path(ff).is_absolute() else job.root / ff
        shutil.copy(src, public / src.name)
    out = d / "captions.mov"
    cmd = ["npx", "remotion", "render", "src/index.ts", "Captions", str(out),
           f"--props={props_path}", f"--public-dir={public}",
           "--codec=prores", "--prores-profile=4444", "--pixel-format=yuva444p10le", "--image-format=png",
           "--color-space=bt709", "--muted", "--log=error", "--overwrite",
           f"--concurrency={os.environ.get('REMOTION_CONCURRENCY', os.cpu_count() or 4)}"]
    browser = os.environ.get("REMOTION_BROWSER") or next((b for b in BROWSERS if Path(b).exists()), None)
    if browser:
        cmd.append(f"--browser-executable={browser}")
    p = subprocess.run(cmd, cwd=REMOTION, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise SystemExit("remotion render failed:\n" + "\n".join(p.stdout.splitlines()[-30:]))
    return out


def composite(job: Job, d: Path, edl: dict, captions: Path | None) -> Path:
    probe = job.probe()
    assets = {a["id"]: a for a in probe["assets"]}
    W, H, fps = edl["canvas"]["width"], edl["canvas"]["height"], edl["canvas"]["fps"]
    inputs = ["-i", str(d / "base.mov")]
    graph, last, n = [], "0:v", 1
    for c in resolve_cutaways(edl, probe):
        a = assets[c["asset"]]
        frames = max(1, to_frame(c["duration"], fps))
        f0 = to_frame(c["at"], fps)
        inputs += ["-ss", f"{c['src_in']:.6f}", "-t", f"{c['duration'] + 0.5:.6f}", "-i", str(job.mezz(a["id"]))]
        # exact rational offsets and frame-number gating: float seconds round a frame late
        graph.append(f"[{n}:v]trim=end_frame={frames},setpts=PTS-STARTPTS+{f0}/({fps}*TB),"
                     f"{fit_filter(a['width'], a['height'], W, H)},format=yuv422p10le[cw{n}]")
        graph.append(f"[{last}][cw{n}]overlay=eof_action=pass:enable='between(n,{f0},{f0 + frames - 1})'[v{n}]")
        last, n = f"v{n}", n + 1
    if captions:
        inputs += ["-i", str(captions)]
        graph.append(f"[{n}:v]format=yuva444p10le[cap]")
        graph.append(f"[{last}][cap]overlay=format=yuv444p10:eof_action=pass,format=yuv422p10le[vout]")
        last = "vout"
    master = d / "master.mov"
    args = inputs[:]
    if graph:
        args += ["-filter_complex", ";".join(graph), "-map", f"[{last}]"]
    else:
        args += ["-map", "0:v"]
    args += ["-map", "0:a", "-r", str(fps), "-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
             "-c:a", "copy", "-movflags", "+write_colr", str(master)]
    ffmpeg(args)
    return master


def render(job: Job, version: str) -> dict:
    d = job.edit_dir(version)
    edl = load(d / "edl.json")
    total_frames = to_frame(duration(edl), edl["canvas"]["fps"])
    cap = render_captions(job, d, edl, total_frames)
    master = composite(job, d, edl, cap)
    return {"captions": cap, "master": master}


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    r = render(Job(sys.argv[1]), sys.argv[2])
    print(f"render: captions={r['captions']} master={r['master']}")


if __name__ == "__main__":
    main()
