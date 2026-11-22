"""Shared helpers for the video-edit pipeline.

Every script works on a JOB directory:

    <job>/
      brief.json                 input contract (from the Reels Agent)
      assets/                    original files, never modified
      work/                      derived data (safe to delete and rebuild)
        probe.json
        mezz/<asset>.mov         ProRes 422 HQ, CFR, Rec.709 mezzanines
        audio/<asset>.wav        16 kHz mono analysis audio
        transcripts/<asset>.json word-level transcripts
        analysis.json            takes, silences, fillers per beat
      edits/<version>/           one folder per draft: v1, v2, ...
        edl.json                 the Edit Decision List (source of truth)
        base.mov                 picture + sound after cuts and cutaways
        captions.mov             transparent caption layer (ProRes 4444)
        master.mov               base + captions (archive, never published)
        exports/*.mp4            platform deliverables
        qa/                      frames, contact sheet, report.json
        edit_log.md
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

FPS_DEFAULT = 30
SKILL_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- process

def run(cmd: list[str], *, quiet: bool = True, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command. Raises with stderr tail on failure."""
    cmd = [str(c) for c in cmd]
    if not quiet:
        print("+", " ".join(cmd), file=sys.stderr)
    p = subprocess.run(cmd, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                       stderr=subprocess.PIPE, text=True)
    if check and p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-25:])
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(cmd[:6])} ...\n{tail}")
    return p


def ffmpeg(args: list, **kw) -> subprocess.CompletedProcess:
    return run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args], **kw)


def ffprobe_json(path: Path) -> dict:
    p = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path], capture=True)
    return json.loads(p.stdout)


def need(binary: str):
    if shutil.which(binary) is None:
        raise SystemExit(f"missing dependency: {binary} (run scripts/setup.sh)")


# ---------------------------------------------------------------- json io

def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------- job layout

class Job:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not (self.root / "brief.json").exists():
            raise SystemExit(f"{self.root} has no brief.json")
        self.brief = normalize_brief(load(self.root / "brief.json"))

    # paths
    @property
    def work(self) -> Path: return self.root / "work"
    def mezz(self, aid: str) -> Path: return self.work / "mezz" / f"{aid}.mov"
    def wav(self, aid: str) -> Path: return self.work / "audio" / f"{aid}.wav"
    def transcript(self, aid: str) -> Path: return self.work / "transcripts" / f"{aid}.json"
    @property
    def probe_path(self) -> Path: return self.work / "probe.json"
    @property
    def analysis_path(self) -> Path: return self.work / "analysis.json"
    def edit_dir(self, version: str) -> Path: return self.root / "edits" / version

    def asset(self, aid: str) -> dict:
        for a in self.brief["assets"]:
            if a["id"] == aid:
                return a
        raise SystemExit(f"unknown asset id: {aid}")

    def asset_src(self, a: dict) -> Path:
        p = Path(a["path"])
        return p if p.is_absolute() else (self.root / p)

    def a_roll(self) -> list[dict]:
        return [a for a in self.brief["assets"] if a["role"] == "a_roll"]

    def probe(self) -> dict:
        if not self.probe_path.exists():
            raise SystemExit("run probe.py first")
        return load(self.probe_path)

    def canvas(self) -> dict:
        return self.probe()["canvas"]

    def versions(self) -> list[str]:
        d = self.root / "edits"
        if not d.exists():
            return []
        return sorted((p.name for p in d.iterdir() if p.is_dir() and re.fullmatch(r"v\d+", p.name)),
                      key=lambda s: int(s[1:]))

    def next_version(self) -> str:
        vs = self.versions()
        return f"v{int(vs[-1][1:]) + 1}" if vs else "v1"


def normalize_brief(b: dict) -> dict:
    """Fill defaults so downstream code can rely on every key."""
    b = dict(b)
    b.setdefault("id", "reel")
    script = b.get("script") or {}
    b["script"] = {
        "hook": script.get("hook", ""),
        "beats": [x if isinstance(x, dict) else {"text": x} for x in script.get("beats", [])],
        "cta": script.get("cta", ""),
        # verbatim: the speaker reads the script word for word (takes are matched against it)
        # points:   the speaker talks freely around talking points (takes are found by repetition)
        "mode": script.get("mode", "verbatim"),
    }
    assets = []
    for i, a in enumerate(b.get("assets", [])):
        a = dict(a)
        a.setdefault("id", f"a{i + 1}")
        a.setdefault("type", "talking_head")
        a.setdefault("role", "a_roll" if a["type"] in ("talking_head", "ai_avatar") else "b_roll")
        a.setdefault("beat_ref", [])
        assets.append(a)
    b["assets"] = assets
    t = b.get("target") or {}
    b["target"] = {
        "platforms": t.get("platforms") or ([t["platform"]] if t.get("platform") else ["instagram", "tiktok", "shorts"]),
        "max_seconds": float(t.get("max_seconds", 60)),
        "language": t.get("language", "he"),
    }
    br = b.get("brand") or {}
    b["brand"] = {
        "caption_font": br.get("caption_font", "Heebo"),
        "primary": br.get("primary", "#FFFFFF"),
        "highlight": br.get("highlight", "#FFD60A"),
        "stroke": br.get("stroke", "#000000"),
        "font_file": br.get("font_file"),
    }
    st = b.get("style") or {}
    b["style"] = {
        "captions": st.get("captions", "bold"),   # bold | quiet | none
        "zoom": bool(st.get("zoom", True)),        # false = never punch in (movement comes from the speaker)
        "continuity": st.get("continuity", "single"),  # single = one camera setup for the whole reel | free
        "notes": st.get("notes", ""),              # free-text editing direction for the editor
    }
    return b


def script_beats(brief: dict) -> list[dict]:
    """Hook, beats and CTA as one ordered list of beats with indices."""
    s = brief["script"]
    beats = []
    if s["hook"]:
        beats.append({"kind": "hook", "text": s["hook"]})
    for x in s["beats"]:
        beats.append({"kind": "beat", **x})
    if s["cta"]:
        beats.append({"kind": "cta", "text": s["cta"]})
    for i, x in enumerate(beats):
        x["index"] = i
    return beats


# ---------------------------------------------------------------- time

def to_frame(t: float, fps: int) -> int:
    return int(round(t * fps))


def frame_time(f: int, fps: int) -> float:
    return f / fps


def tc(t: float) -> str:
    """Seconds -> m:ss.ff style timecode for humans."""
    m = int(t // 60)
    s = t - 60 * m
    return f"{m}:{s:05.2f}"


# ---------------------------------------------------------------- text

NIQQUD = re.compile(r"[֑-ׇ]")
FINALS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})
PUNCT = re.compile(r"[^\w֐-׿']+", re.UNICODE)


def norm_word(w: str) -> str:
    """Comparison key for a word: no niqqud, no punctuation, finals folded, lowercase."""
    w = unicodedata.normalize("NFC", w)
    w = NIQQUD.sub("", w)
    w = w.replace("״", "").replace("׳", "'").replace('"', "")
    w = PUNCT.sub("", w).lower().translate(FINALS)
    return w


def tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", text.strip()) if t]


FILLERS_HE = {"אה", "אהה", "אההה", "אמ", "אממ", "אמממ", "אם", "הממ", "המ", "אוקיי", "כאילו", "יעני", "בעצם"}
FILLERS_EN = {"um", "umm", "uh", "uhh", "er", "erm", "hmm", "like", "basically"}
# words that are fillers only when standing alone (not inside a phrase) are judged by the agent;
# these are the unconditional ones that autocut removes by default.
HARD_FILLERS = {"אה", "אהה", "אההה", "אמ", "אממ", "אמממ", "הממ", "המ", "um", "umm", "uh", "uhh", "er", "erm", "hmm"}


def is_filler(w: str, hard_only: bool = True) -> bool:
    k = norm_word(w)
    if hard_only:
        return k in {norm_word(x) for x in HARD_FILLERS}
    return k in {norm_word(x) for x in FILLERS_HE | FILLERS_EN}


# ---------------------------------------------------------------- audio envelope

def load_wav16k(path: Path):
    import numpy as np
    import wave
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1, "analysis wav must be 16k mono"
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype="<i2").astype("float32") / 32768.0


class Envelope:
    """RMS energy in 5 ms hops, in dBFS. Used to place cuts in the quietest spot."""
    HOP = 0.005

    def __init__(self, wav: Path):
        import numpy as np
        x = load_wav16k(wav)
        hop = int(16000 * self.HOP)
        n = len(x) // hop
        frames = x[: n * hop].reshape(n, hop)
        rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
        self.db = 20 * np.log10(rms)
        self.duration = len(x) / 16000

    def quietest(self, t: float, window: float, lo: float | None = None, hi: float | None = None) -> float:
        """Time of minimum energy within [t-window, t+window], clamped to [lo, hi]."""
        import numpy as np
        a = max(0.0, t - window, lo if lo is not None else 0.0)
        b = min(self.duration, t + window, hi if hi is not None else self.duration)
        if b - a < self.HOP * 2:
            return t
        i0, i1 = int(a / self.HOP), int(b / self.HOP)
        seg = self.db[i0:i1]
        if len(seg) == 0:
            return t
        # prefer the minimum closest to t among values within 1.5 dB of the minimum
        m = seg.min()
        cand = np.where(seg <= m + 1.5)[0]
        times = (i0 + cand) * self.HOP + self.HOP / 2
        return float(times[np.argmin(np.abs(times - t))])

    def level(self, a: float, b: float) -> float:
        i0, i1 = int(a / self.HOP), max(int(a / self.HOP) + 1, int(b / self.HOP))
        seg = self.db[i0:i1]
        return float(seg.mean()) if len(seg) else -120.0

    def noise_floor(self) -> float:
        import numpy as np
        return float(np.percentile(self.db, 10))


def ceil_even(x: float) -> int:
    v = int(math.ceil(x))
    return v + (v % 2)
