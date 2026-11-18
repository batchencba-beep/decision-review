#!/usr/bin/env python3
"""Cut the spoken track: one frame-exact ProRes clip per segment, then a lossless concat.

usage: cut.py <job> <version>        (build.py calls this)

Each segment is rendered from the mezzanine with:
  * exact frame count (trim by frame, never by keyframe / stream copy)
  * sample-exact audio of the same length + 12 ms micro-fades, so no cut ever clicks
  * cover-fit to the canvas, optional punch-in zoom around an anchor point
Clips are cached in work/segcache by content hash, so a revision only re-renders the segments it touched.
The clips are joined with the concat demuxer (stream copy: no generation loss) -> edits/<v>/base.mov
"""
import hashlib
import json
import sys

from common import Job, ffmpeg, load
from edl import timeline

SR = 48000


def even(x: float) -> int:
    v = int(round(x))
    return v + (v % 2)


def fit_filter(aw: int, ah: int, W: int, H: int, zoom: float = 1.0, anchor=(0.5, 0.4)) -> str:
    s = max(W / aw, H / ah) * zoom
    sw, sh = max(W, even(aw * s)), max(H, even(ah * s))
    x = min(max(0, round(sw * anchor[0] - W / 2)), sw - W)
    y = min(max(0, round(sh * anchor[1] - H / 2)), sh - H)
    return f"scale={sw}:{sh}:flags=lanczos,crop={W}:{H}:{x}:{y},setsar=1"


def segment_clip(job: Job, seg: dict, asset: dict, canvas: dict, fade_ms: int):
    fps, W, H = canvas["fps"], canvas["width"], canvas["height"]
    key = json.dumps([asset["id"], str(job.mezz(asset["id"]).stat().st_mtime), seg["f_in"], seg["frames"],
                      seg.get("zoom", 1.0), seg.get("anchor"), W, H, fps, fade_ms], sort_keys=True)
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    out = job.work / "segcache" / f"{h}.mov"
    if out.exists():
        return out, False
    out.parent.mkdir(parents=True, exist_ok=True)
    n = seg["frames"]
    dur = n / fps
    samples = round(dur * SR)
    fade = min(fade_ms / 1000, dur / 4)
    vf = (f"trim=end_frame={n},setpts=PTS-STARTPTS,"
          + fit_filter(asset["width"], asset["height"], W, H, float(seg.get("zoom", 1.0)),
                       tuple(seg.get("anchor") or (0.5, 0.4)))
          + ",format=yuv422p10le")
    af = (f"atrim=end_sample={samples},asetpts=PTS-STARTPTS,apad=whole_len={samples},"
          f"afade=t=in:d={fade:.4f},afade=t=out:st={dur - fade:.4f}:d={fade:.4f}")
    start = seg["f_in"] / fps
    tmp = out.with_suffix(".part.mov")
    ffmpeg(["-ss", f"{start:.6f}", "-t", f"{dur + 0.5:.6f}", "-i", str(job.mezz(asset["id"])),
            "-filter_complex", f"[0:v]{vf}[v];[0:a]{af}[a]", "-map", "[v]", "-map", "[a]",
            "-r", str(fps), "-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
            "-c:a", "pcm_s16le", "-ar", str(SR), "-ac", "2", "-f", "mov", str(tmp)])
    tmp.rename(out)
    return out, True


def cut(job: Job, version: str) -> dict:
    d = job.edit_dir(version)
    edl = load(d / "edl.json")
    probe = job.probe()
    assets = {a["id"]: a for a in probe["assets"]}
    canvas = edl["canvas"]
    fade = int(edl.get("audio", {}).get("fade_ms", 12))
    clips, rendered = [], 0
    for seg in timeline(edl):
        if seg["frames"] <= 0:
            continue
        clip, new = segment_clip(job, seg, assets[seg["asset"]], canvas, fade)
        clips.append(clip)
        rendered += new
    lst = d / "segments.txt"
    lst.write_text("".join(f"file '{c}'\n" for c in clips))
    base = d / "base.mov"
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+write_colr", str(base)])
    return {"segments": len(clips), "rendered": rendered, "cached": len(clips) - rendered, "base": base}


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    r = cut(Job(sys.argv[1]), sys.argv[2])
    print(f"cut: {r['segments']} segments ({r['rendered']} rendered, {r['cached']} cached) -> {r['base']}")


if __name__ == "__main__":
    main()
