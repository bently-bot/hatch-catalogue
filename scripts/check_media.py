#!/usr/bin/env python3
"""Check every screenshot and icon URL in a built catalogue, fix what can be fixed, and fail when the source looks broken.

For each app: every screenshot URL and an absolute iconUrl must answer 200 with an image content type, within a timeout,
with retries for transient errors. Dead screenshots are dropped and dead icons cleared, so the app never gets a URL that
can't load. Featured apps' working screenshots are mirrored into dist/shots/ and published as release assets
(upstream media hashes change whenever appstream.debian.org regenerates, so the most-seen shots don't depend on it).
Exit 1 when more than --max-broken percent of the apps with screenshots had a broken one (a stale DEP-11 source, an
outage): that's a catalogue problem to look at, not something to publish.

usage: check_media.py dist [--max-broken 3] [--workers 32] [--no-mirror] [--report dist/media-report.json]"""
import argparse, concurrent.futures as cf, json, os, sys, time, urllib.error, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("dist")
ap.add_argument("--max-broken", type=float, default=3.0, help="percent of apps with screenshots allowed to have a dead one")
ap.add_argument("--workers", type=int, default=32)
ap.add_argument("--timeout", type=float, default=15)
ap.add_argument("--no-mirror", action="store_true")
ap.add_argument("--mirror-base", default="https://github.com/bently-bot/hatch-catalogue/releases/latest/download/")
ap.add_argument("--report", default=None)
ap.add_argument("--mirror-max-kb", type=int, default=600, help="bigger shots stay upstream (keeps releases small)")
a = ap.parse_args()
UA = "hatch-catalogue-media-check (+https://github.com/bently-bot/hatch-catalogue)"
path = os.path.join(a.dist, "catalogue.json")
cat = json.load(open(path))

def probe(url, want_body=False):
    """(ok, reason, body|None). GET (not HEAD: some CDNs answer HEAD differently); body read only when mirroring."""
    last = "?"
    for attempt in range(3):
        if attempt: time.sleep(1.5 * attempt)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*"})
            with urllib.request.urlopen(req, timeout=a.timeout) as r:
                ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if r.status != 200: last = f"HTTP {r.status}"; continue
                if not ctype.startswith("image/"): return False, f"content-type {ctype or 'missing'}", None
                body = r.read() if want_body else r.read(1)
                if not body: last = "empty body"; continue
                return True, "ok", body if want_body else None
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (403, 404, 410): break      # permanent
        except Exception as e:
            last = type(e).__name__ + (f": {e.reason}" if hasattr(e, "reason") else "")
    return False, last, None

featured = {x["id"] for x in cat["apps"] if x.get("featured")}
jobs = {}
for x in cat["apps"]:
    for i, u in enumerate(x.get("screenshots") or []):
        if u.startswith("http"): jobs[(x["id"], "shot", i)] = u
    if (x.get("iconUrl") or "").startswith("http"): jobs[(x["id"], "icon", 0)] = x["iconUrl"]

t0 = time.time()
res = {}
with cf.ThreadPoolExecutor(a.workers) as ex:
    futs = {ex.submit(probe, u, not a.no_mirror and k[1] == "shot" and k[0] in featured): k for k, u in jobs.items()}
    for f in cf.as_completed(futs): res[futs[f]] = f.result()

broken_apps, dead = [], []
shots_dir = os.path.join(a.dist, "shots"); os.makedirs(shots_dir, exist_ok=True)
mirrored = 0
for x in cat["apps"]:
    shots = x.get("screenshots") or []
    keep, bad = [], 0
    for i, u in enumerate(shots):
        ok, why, body = res.get((x["id"], "shot", i), (True, "not checked", None))
        if not ok: bad += 1; dead.append({"id": x["id"], "url": u, "reason": why}); continue
        if body and len(body) <= a.mirror_max_kb * 1024:
            ext = os.path.splitext(u.split("?")[0])[1].lower()
            ext = ext if ext in (".png", ".jpg", ".jpeg", ".webp") else ".png"
            name = f"shot-{x['id']}-{len(keep) + 1}{ext}"
            open(os.path.join(shots_dir, name), "wb").write(body); mirrored += 1
            u = a.mirror_base + name
        keep.append(u)
    if bad: broken_apps.append(x["id"])
    if shots:
        if keep: x["screenshots"] = keep
        else: x.pop("screenshots", None)
    ok, why, _ = res.get((x["id"], "icon", 0), (True, "", None))
    if not ok: dead.append({"id": x["id"], "url": x["iconUrl"], "reason": "icon: " + why}); x.pop("iconUrl", None)

with_shots = sum(1 for k in jobs if k[1] == "shot" and k[2] == 0)
pct = 100.0 * len(broken_apps) / max(1, with_shots)
summary = (f"media check: {len(jobs)} URLs in {time.time() - t0:.0f}s; {len(dead)} dead; "
           f"{len(broken_apps)}/{with_shots} apps with screenshots had a broken one ({pct:.1f}%, limit {a.max_broken}%); "
           f"{mirrored} featured screenshots mirrored")
print(summary)
for d in dead[:40]: print(f"  dead {d['id']}: {d['reason']}  {d['url']}")
if len(dead) > 40: print(f"  … {len(dead) - 40} more")

s = json.dumps(cat, ensure_ascii=False, separators=(",", ":"))
open(path, "w").write(s)
import gzip
with gzip.open(os.path.join(a.dist, "catalogue.json.gz"), "wb", 9) as g: g.write(s.encode())
if a.report: json.dump({"summary": summary, "brokenApps": broken_apps, "dead": dead}, open(a.report, "w"), indent=1)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        f.write(f"### Screenshots & icons\n{summary}\n\n")
        if dead:
            f.write("| app | reason | url |\n|---|---|---|\n")
            for d in dead[:100]: f.write(f"| {d['id']} | {d['reason']} | {d['url']} |\n")
sys.exit(1 if pct > a.max_broken else 0)
