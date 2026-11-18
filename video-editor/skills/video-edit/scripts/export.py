#!/usr/bin/env python3
"""Platform exports from master.mov — the one and only lossy encode.

usage: export.py <job> <version>          (build.py calls this)

  exports/instagram.mp4        1080x1920  H.264 High, CRF 16 capped at 20 Mb/s   (Instagram shows ~1080 wide;
                                                                                  a clean 1080 file survives its
                                                                                  re-compression best)
  exports/tiktok_shorts.mp4    2160x3840  H.264 High, CRF 17 capped at 45 Mb/s   (only when the canvas is 4K)

Audio: two-pass EBU R128 loudness normalisation to -14 LUFS integrated, true peak ≤ -1 dBTP, AAC 320k.
Colour: Rec.709 tags written explicitly so phones don't guess (a guess is how videos come out washed out).
"""
import json
import sys

from common import Job, ffmpeg, run

TARGET = {"I": -14.0, "TP": -1.0, "LRA": 11.0}


def measure_loudness(src) -> dict:
    p = run(["ffmpeg", "-hide_banner", "-nostdin", "-i", src, "-vn", "-af",
             f"loudnorm=I={TARGET['I']}:TP={TARGET['TP']}:LRA={TARGET['LRA']}:print_format=json", "-f", "null", "-"],
            capture=True)
    txt = p.stderr
    return json.loads(txt[txt.rindex("{"): txt.rindex("}") + 1])


def audio_filter(m: dict) -> str:
    return (f"loudnorm=I={TARGET['I']}:TP={TARGET['TP']}:LRA={TARGET['LRA']}"
            f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
            f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")


def encode(master, out, w, h, crf, maxrate, level, af, fps):
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg(["-i", str(master),
            "-vf", f"scale={w}:{h}:flags=lanczos+accurate_rnd+full_chroma_int:out_color_matrix=bt709,format=yuv420p",
            "-af", af, "-r", str(fps),
            "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-level", level,
            "-crf", str(crf), "-maxrate", maxrate, "-bufsize", f"{2 * int(maxrate[:-1])}M",
            "-g", str(2 * fps), "-bf", "2",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(out)])


def export(job: Job, version: str) -> list:
    d = job.edit_dir(version)
    master = d / "master.mov"
    canvas = job.canvas()
    fps = canvas["fps"]
    platforms = job.brief["target"]["platforms"]
    af = audio_filter(measure_loudness(master))
    outs = []
    ig = d / "exports" / "instagram.mp4"
    encode(master, ig, 1080, 1920, 16, "20M", "4.2", af, fps)
    outs.append(ig)
    if canvas["width"] >= 2160 and any(p in platforms for p in ("tiktok", "shorts", "youtube")):
        tt = d / "exports" / "tiktok_shorts.mp4"
        encode(master, tt, canvas["width"], canvas["height"], 17, "45M", "5.1", af, fps)
        outs.append(tt)
    return outs


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    for o in export(Job(sys.argv[1]), sys.argv[2]):
        print(f"export: {o}")


if __name__ == "__main__":
    main()
