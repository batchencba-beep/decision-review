#!/usr/bin/env python3
"""Build a draft from its EDL: validate → snap → captions → cut → render → export → QA.

usage: build.py <job> <version> [--no-snap] [--no-transcribe-qa]

Run this after every EDL change. It refuses to render an EDL with errors (cuts through words, bad
zooms, cutaways outside the timeline) and prints why. Segment clips are cached, so a revision that
touches two segments re-renders two segments.
"""
import sys
import time

from captions import build_captions
from common import Job, load, save
from cut import cut
from edl import snap, validate
from export import export
from render import render


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(args) != 2:
        raise SystemExit(__doc__)
    job, version = Job(args[0]), args[1]
    path = job.edit_dir(version) / "edl.json"
    edl = load(path)
    edl["version"] = version
    t0 = time.time()

    if "--no-snap" not in sys.argv:
        changes = snap(job, edl)
        if changes:
            print(f"snap: moved {len(changes)} boundaries: " + ", ".join(changes[:8]))
    errors, warns = validate(job, edl)
    for w in warns:
        print(f"warn: {w}")
    if errors:
        save(path, edl)
        for e in errors:
            print(f"ERROR: {e}")
        raise SystemExit("EDL has errors — fix them and build again")
    edl["captions"]["chunks"] = build_captions(job, edl)
    save(path, edl)
    print(f"captions: {len(edl['captions']['chunks'])} chunks")

    step = time.time()
    r = cut(job, version)
    print(f"cut: {r['segments']} segments ({r['rendered']} rendered, {r['cached']} cached) {time.time() - step:.0f}s")
    step = time.time()
    render(job, version)
    print(f"render: captions + composite {time.time() - step:.0f}s")
    step = time.time()
    outs = export(job, version)
    print(f"export: {', '.join(o.name for o in outs)} {time.time() - step:.0f}s")

    import subprocess
    qa_args = [sys.executable, str(__import__('pathlib').Path(__file__).with_name("qa.py")), str(job.root), version]
    if "--no-transcribe-qa" in sys.argv:
        qa_args.append("--no-transcribe")
    subprocess.run(qa_args, check=False)
    print(f"build {version} done in {time.time() - t0:.0f}s -> {job.edit_dir(version)}")


if __name__ == "__main__":
    main()
