#!/usr/bin/env python3
"""Step 2 — convert every asset to an edit-safe mezzanine.

usage: ingest.py <job> [--force]

For each asset:
  work/mezz/<id>.mov    ProRes 422 HQ, 10-bit 4:2:2, constant 30 fps, Rec.709, PCM 48 kHz stereo
  work/audio/<id>.wav   16 kHz mono (a_roll only) for transcription and cut analysis

Why: iPhone footage is variable-frame-rate HEVC, often HLG HDR. Cutting it directly drifts captions,
lands cuts on the wrong frame and washes colours out. Every later step reads only the mezzanine,
and the only lossy encode in the whole pipeline is the final export.
"""
import sys

from common import Job, ffmpeg, need

HDR_IN = {"arib-std-b67": "arib-std-b67", "smpte2084": "smpte2084"}


def video_filter(a: dict, fps: int) -> str:
    chain = []
    if "hdr" in a["flags"]:
        tin = HDR_IN[a["color_transfer"]]
        chain += [
            f"zscale=tin={tin}:min=bt2020nc:pin=bt2020:rin=tv:t=linear:npl=100",
            "format=gbrpf32le",
            "zscale=p=bt709",
            "tonemap=tonemap=hable:desat=0",
            "zscale=t=bt709:m=bt709:r=tv",
        ]
    elif (a.get("color_space") or "") in ("smpte170m", "bt470bg"):
        chain.append("zscale=min=%s:m=bt709:pin=%s:p=bt709:tin=bt709:t=bt709:r=tv" % (
            a["color_space"], "smpte170m" if a["color_space"] == "smpte170m" else "bt470bg"))
    chain += [f"fps={fps}", "scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos", "format=yuv422p10le",
              "setsar=1"]
    return ",".join(chain)


def ingest_asset(job: Job, a: dict, fps: int, force: bool):
    src = a["path"]
    out = job.mezz(a["id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    from pathlib import Path
    if not force and out.exists() and out.stat().st_mtime > Path(src).stat().st_mtime:
        print(f"  {a['id']}: mezzanine up to date")
    else:
        args = ["-i", src, "-map", "0:v:0", "-vf", video_filter(a, fps),
                "-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0", "-bits_per_mb", "8000",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]
        if a["audio"]:
            args += ["-map", "0:a:0", "-af", "aresample=48000:async=1:first_pts=0", "-ac", "2",
                     "-c:a", "pcm_s16le"]
        args += ["-map_metadata", "-1", "-movflags", "+write_colr", str(out)]
        what = "tone-map HDR→709, " if "hdr" in a["flags"] else ""
        print(f"  {a['id']}: {what}CFR {fps}fps ProRes HQ -> {out.name}")
        ffmpeg(args)
    if a["role"] == "a_roll" and a["audio"]:
        wav = job.wav(a["id"])
        wav.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg(["-i", str(out), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    need("ffmpeg")
    job = Job(args[0])
    probe = job.probe()
    fps = probe["canvas"]["fps"]
    for a in probe["assets"]:
        ingest_asset(job, a, fps, "--force" in sys.argv)
    print("ingest done")


if __name__ == "__main__":
    main()
