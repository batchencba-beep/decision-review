#!/usr/bin/env python3
"""Check an EDL without rendering. --snap also fixes boundaries (out of words, onto quiet frames).

usage: validate_edl.py <job> <version> [--snap]
"""
import sys

from common import Job, load, save, tc
from edl import duration, snap, timeline, validate


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(args) != 2:
        raise SystemExit(__doc__)
    job = Job(args[0])
    path = job.edit_dir(args[1]) / "edl.json"
    edl = load(path)
    if "--snap" in sys.argv:
        ch = snap(job, edl)
        save(path, edl)
        print(f"snapped {len(ch)} boundaries")
    errors, warns = validate(job, edl)
    for s in timeline(edl):
        print(f"  {s['id']:<4} {s['asset']} {tc(s['in'])}–{tc(s['out'])} -> {tc(s['o_start'])}–{tc(s['o_end'])} {s.get('reason', '')}")
    print(f"duration {duration(edl):.2f}s")
    for w in warns:
        print(f"warn: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
