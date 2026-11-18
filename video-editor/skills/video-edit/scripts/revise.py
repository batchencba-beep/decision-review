#!/usr/bin/env python3
"""Start a revision: copy edits/<from>/edl.json to the next version folder. Never overwrite a draft.

usage: revise.py <job> [--from v1]

Prints the new version name. Then edit edits/<new>/edl.json (segments, cutaways, captions.overrides,
captions.emphasis, style ...) and run build.py <job> <new>.
"""
import sys

from common import Job, load, save


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    job = Job(args[0])
    vs = job.versions()
    if not vs:
        raise SystemExit("no drafts yet — run autocut.py first")
    src = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else vs[-1]
    new = job.next_version()
    edl = load(job.edit_dir(src) / "edl.json")
    edl["version"] = new
    edl["revised_from"] = src
    edl["notes"] = []
    save(job.edit_dir(new) / "edl.json", edl)
    print(new)


if __name__ == "__main__":
    main()
