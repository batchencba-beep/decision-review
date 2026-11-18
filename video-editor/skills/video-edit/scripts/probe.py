#!/usr/bin/env python3
"""Step 1 — inspect every asset in the brief and decide the working canvas.

usage: probe.py <job>

Writes work/probe.json and prints a human summary. Flags (never silently fixed later):
  vfr           variable frame rate (iPhone default) -> ingest converts to CFR
  hdr           HLG/PQ transfer (iPhone "HDR Video") -> ingest tone-maps to Rec.709
  low_res       short side < 1080
  orientation   a_roll that is not vertical
  clipping      audio peaks at 0 dBFS
  no_audio      a_roll without sound
"""
import sys
from fractions import Fraction

from common import FPS_DEFAULT, Job, ffprobe_json, need, run, save


def rate(s: str) -> float:
    try:
        return float(Fraction(s)) if s and s != "0/0" else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def rotation(v: dict) -> int:
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            return int(round(float(sd["rotation"]))) % 360
    r = (v.get("tags") or {}).get("rotate")
    return int(r) % 360 if r else 0


def frame_jitter(path) -> float:
    """Spread of frame durations over the first ~10 s (seconds). 0 for true CFR."""
    p = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals", "%+10",
             "-show_entries", "frame=pts_time", "-of", "csv=p=0", path], capture=True, check=False)
    ts = sorted(float(x) for x in p.stdout.split() if x.replace(".", "", 1).replace("-", "", 1).isdigit())
    if len(ts) < 3:
        return 0.0
    d = [b - a for a, b in zip(ts, ts[1:])]
    return max(d) - min(d)


def peak_db(path) -> float | None:
    p = run(["ffmpeg", "-hide_banner", "-nostdin", "-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"],
            capture=True, check=False)
    for line in p.stderr.splitlines():
        if "max_volume:" in line:
            return float(line.split("max_volume:")[1].split()[0])
    return None


def probe_asset(job: Job, a: dict) -> dict:
    src = job.asset_src(a)
    if not src.exists():
        raise SystemExit(f"asset {a['id']} not found: {src}")
    info = ffprobe_json(src)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        raise SystemExit(f"asset {a['id']} has no video stream")
    rot = rotation(v)
    w, h = int(v["width"]), int(v["height"])
    if rot in (90, 270):
        w, h = h, w
    r_rate, avg_rate = rate(v.get("r_frame_rate")), rate(v.get("avg_frame_rate"))
    jitter = frame_jitter(src)
    trc = v.get("color_transfer") or ""
    bits = int(v.get("bits_per_raw_sample") or (10 if "10" in (v.get("pix_fmt") or "") else 8))
    dur = float(info["format"].get("duration") or v.get("duration") or 0)
    out = {
        "id": a["id"], "path": str(src), "type": a["type"], "role": a["role"],
        "width": w, "height": h, "rotation": rot, "codec": v.get("codec_name"),
        "pix_fmt": v.get("pix_fmt"), "bit_depth": bits,
        "color_transfer": trc, "color_primaries": v.get("color_primaries"), "color_space": v.get("color_space"),
        "r_frame_rate": round(r_rate, 3), "avg_frame_rate": round(avg_rate, 3), "frame_jitter": round(jitter, 4),
        "duration": round(dur, 3),
        "audio": None, "flags": [],
    }
    if au:
        out["audio"] = {"codec": au.get("codec_name"), "sample_rate": int(au.get("sample_rate", 0)),
                        "channels": int(au.get("channels", 0)), "peak_db": peak_db(src)}
    f = out["flags"]
    if jitter > 0.002 or (avg_rate and abs(r_rate - avg_rate) > 0.05):
        f.append("vfr")
    if trc in ("arib-std-b67", "smpte2084"):
        f.append("hdr")
    if min(w, h) < 1080:
        f.append("low_res")
    if a["role"] == "a_roll" and h <= w:
        f.append("orientation")
    if a["role"] == "a_roll" and not au:
        f.append("no_audio")
    if au and out["audio"]["peak_db"] is not None and out["audio"]["peak_db"] >= -0.1:
        f.append("clipping")
    return out


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    need("ffmpeg"); need("ffprobe")
    job = Job(sys.argv[1])
    assets = [probe_asset(job, a) for a in job.brief["assets"]]
    a_roll = [x for x in assets if x["role"] == "a_roll"]
    if not a_roll:
        raise SystemExit("brief has no a_roll asset (talking head / speech-carrying clip)")
    # 4K canvas only when the speech footage itself is 4K: never upscale the main picture.
    four_k = all(min(x["width"], x["height"]) >= 2160 for x in a_roll)
    canvas = {"width": 2160, "height": 3840, "fps": FPS_DEFAULT} if four_k else {"width": 1080, "height": 1920, "fps": FPS_DEFAULT}
    data = {"canvas": canvas, "assets": assets}
    save(job.probe_path, data)

    print(f"canvas {canvas['width']}x{canvas['height']} @ {canvas['fps']}fps")
    for x in assets:
        flags = ",".join(x["flags"]) or "ok"
        print(f"  {x['id']:<6} {x['role']:<6} {x['width']}x{x['height']} {x['codec']} "
              f"{x['avg_frame_rate']}fps {x['bit_depth']}bit trc={x['color_transfer'] or '-'} "
              f"{x['duration']:.2f}s  [{flags}]")
    print(f"-> {job.probe_path}")


if __name__ == "__main__":
    main()
