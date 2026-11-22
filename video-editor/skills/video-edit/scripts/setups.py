#!/usr/bin/env python3
"""Camera setups: which stretches of footage share the same framing.

usage: setups.py <job>          (analyze.py calls this; run alone to inspect)

A "setup" is one camera position + framing. Cutting from one setup to another between sentences reads as
a crude jump (the speaker teleports on the sofa), so the editor builds a reel from ONE setup unless the
brief allows otherwise (style.continuity).

How it is detected — from the picture, not from file names:
  * every a_roll mezzanine is sampled at 2 fps into tiny normalised greyscale thumbnails
  * inside a file, a setup change is a SUSTAINED shift: the median picture of the 3 s before and the
    3 s after differ far more than the picture varies within those 3 s (a person moving does not trigger
    it; moving the phone or the person changing place does)
  * stretches from every file are then clustered by their median picture, so two files shot from the
    same position count as the same setup, and one file with two positions counts as two

Writes work/setups.json: {"setups": {"A": {...}}, "spans": [{"asset", "start", "end", "setup"}]}
and work/setups/<setup>.jpg — one frame per setup, to LOOK at.
"""
import subprocess
import sys

import numpy as np

from common import Job, ffmpeg, save

FPS = 2
W, H = 24, 42
WIN = 3 * FPS               # 3 s windows
SHIFT_MIN = 0.45            # minimum before/after difference for a setup change
SHIFT_RATIO = 3.0           # ... and it must dwarf the movement inside the windows
SAME_SETUP = 0.40           # stretches closer than this share a setup


def thumbs(path) -> np.ndarray:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path), "-an",
                        "-vf", f"fps={FPS},scale={W}:{H}:flags=area,format=gray", "-f", "rawvideo", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise SystemExit(f"thumbnail extraction failed for {path}: {p.stderr.decode()[-400:]}")
    f = np.frombuffer(p.stdout, dtype=np.uint8).astype("float32")
    n = len(f) // (W * H)
    f = f[: n * W * H].reshape(n, H, W)
    # normalise brightness/contrast per frame: exposure drift must not look like a new setup
    m = f.mean(axis=(1, 2), keepdims=True)
    s = f.std(axis=(1, 2), keepdims=True) + 1e-3
    return (f - m) / s


def dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


def change_points(fr: np.ndarray) -> list[int]:
    n = len(fr)
    scores = np.zeros(n)
    for t in range(WIN, n - WIN):
        before, after = fr[t - WIN:t], fr[t:t + WIN]
        mb, ma = np.median(before, axis=0), np.median(after, axis=0)
        d = dist(mb, ma)
        within = max(np.abs(before - mb).mean(), np.abs(after - ma).mean(), 1e-3)
        if d > SHIFT_MIN and d > SHIFT_RATIO * within:
            scores[t] = d
    cps, t = [], 0
    while t < n:
        if scores[t] > 0:
            j = t
            while j + 1 < n and scores[j + 1] > 0:
                j += 1
            cps.append(int(t + np.argmax(scores[t:j + 1])))
            t = j + 1 + WIN
        else:
            t += 1
    return cps


def detect(job: Job) -> dict:
    stretches = []
    for a in job.a_roll():
        fr = thumbs(job.mezz(a["id"]))
        if len(fr) == 0:
            continue
        bounds = [0] + change_points(fr) + [len(fr)]
        for s, e in zip(bounds, bounds[1:]):
            if e - s < 2:
                continue
            stretches.append({"asset": a["id"], "start": s / FPS, "end": e / FPS,
                              "sig": np.median(fr[s:e], axis=0)})
    setups = []          # [{"name", "sig", "seconds"}]
    for st in stretches:
        best = min(setups, key=lambda x: dist(x["sig"], st["sig"]), default=None)
        if best is not None and dist(best["sig"], st["sig"]) < SAME_SETUP:
            st["setup"] = best["name"]
            best["seconds"] += st["end"] - st["start"]
        else:
            name = chr(ord("A") + len(setups))
            setups.append({"name": name, "sig": st["sig"], "seconds": st["end"] - st["start"],
                           "first": (st["asset"], st["start"])})
            st["setup"] = name
    out_dir = job.work / "setups"
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.jpg"):
        f.unlink()
    info = {}
    for s in setups:
        aid, t = s["first"]
        span = next(x for x in stretches if x["setup"] == s["name"])
        mid = (span["start"] + span["end"]) / 2
        img = out_dir / f"{s['name']}.jpg"
        ffmpeg(["-ss", f"{mid:.2f}", "-i", str(job.mezz(aid)), "-frames:v", "1", "-vf", "scale=360:-2",
                "-q:v", "3", str(img)])
        info[s["name"]] = {"seconds": round(s["seconds"], 1), "frame": str(img)}
    data = {"setups": info,
            "spans": [{"asset": x["asset"], "start": round(x["start"], 2), "end": round(x["end"], 2),
                       "setup": x["setup"]} for x in stretches]}
    save(job.work / "setups.json", data)
    return data


def setup_at(data: dict, asset: str, t: float) -> str | None:
    for s in data["spans"]:
        if s["asset"] == asset and s["start"] - 0.5 <= t < s["end"] + 0.5:
            return s["setup"]
    return None


def setup_of_span(data: dict, asset: str, a: float, b: float) -> str | None:
    """Setup covering most of [a, b]."""
    cover = {}
    for s in data["spans"]:
        if s["asset"] == asset:
            o = min(b, s["end"]) - max(a, s["start"])
            if o > 0:
                cover[s["setup"]] = cover.get(s["setup"], 0) + o
    return max(cover, key=cover.get) if cover else None


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    job = Job(sys.argv[1])
    data = detect(job)
    print(f"{len(data['setups'])} camera setup(s):")
    for name, s in data["setups"].items():
        print(f"  {name}: {s['seconds']}s of footage — look at {s['frame']}")
    for s in data["spans"]:
        print(f"    {s['asset']} {s['start']:.1f}–{s['end']:.1f}s -> {s['setup']}")


if __name__ == "__main__":
    main()
