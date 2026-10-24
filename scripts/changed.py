#!/usr/bin/env python3
"""Ids of curated entries added or changed between two git revisions (for the PR install/launch proof).
usage: changed.py BASE_REF [HEAD_REF]"""
import json, subprocess, sys
def load(ref):
    try: return {a["id"]: a for a in json.loads(subprocess.check_output(["git", "show", f"{ref}:curated.json"]))["apps"]}
    except subprocess.CalledProcessError: return {}
base, head = load(sys.argv[1]), load(sys.argv[2] if len(sys.argv) > 2 else "HEAD")
icons = subprocess.run(["git", "diff", "--name-only", sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "HEAD", "--", "icons"], capture_output=True, text=True).stdout.split()
touched = {p.split("/")[-1].removesuffix(".png") for p in icons}
print(" ".join(sorted(i for i, a in head.items() if base.get(i) != a or i in touched)))
