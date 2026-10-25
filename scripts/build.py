#!/usr/bin/env python3
"""Build dist/catalogue.json(.gz): curated.json entries + every desktop app in Debian 13 (trixie) AppStream/DEP-11.
Icons: curated icons/<id>.png plus 128px DEP-11 icons for featured apps → dist/icons/<id>.png (published as flat
release assets "<id>.png"; the app resolves a relative "icons/<id>.png" iconUrl against the catalogue URL).
usage: build.py [--cache /tmp/dep11] [--out dist]"""
import argparse, datetime, gzip, html, io, json, os, re, shutil, tarfile, urllib.request
import yaml

ap = argparse.ArgumentParser()
ap.add_argument("--arch", default="arm64")
ap.add_argument("--cache", default="/tmp/dep11")
ap.add_argument("--root", default=os.path.join(os.path.dirname(__file__), ".."))
ap.add_argument("--out", default="dist")
a = ap.parse_args()
ROOT = os.path.abspath(a.root)
# appstream.debian.org's own copy of the DEP-11 data is regenerated together with its media, so its screenshot/icon
# URLs resolve; the archive mirror's dep11/ can lag behind by months and point at media hashes that are long gone
# (every screenshot 404'd in Hatch 0.1.0). The mirror is only a fallback when appstream.debian.org is down.
SOURCES = ["https://appstream.debian.org/data/trixie/main", "https://deb.debian.org/debian/dists/trixie/main/dep11"]
MEDIA = "https://appstream.debian.org/media/trixie/"
THUMB = 752   # Hatch shows ~300×200 dp shots; 752 px is sharp on a Fold and ~5× smaller than the originals
os.makedirs(a.cache, exist_ok=True)

def fetch(name):
    p = os.path.join(a.cache, name)
    if not os.path.exists(p):
        err = None
        for base in SOURCES:
            try:
                req = urllib.request.Request(f"{base}/{name}", headers={"User-Agent": "hatch-catalogue-build"})
                with urllib.request.urlopen(req, timeout=120) as r, open(p + ".part", "wb") as f: shutil.copyfileobj(r, f)
                os.replace(p + ".part", p); print(f"{name} from {base}"); break
            except Exception as e:
                err = e; print(f"warning: {base}/{name}: {e}")
        else:
            raise SystemExit(f"can't fetch {name}: {err}")
    return p

def shot_url(s):
    """Thumbnail closest to THUMB px wide; the original when only small thumbs exist and it isn't huge."""
    th = [t for t in s.get("thumbnails") or [] if t.get("url")]
    src = s.get("source-image") or {}
    best = min(th, key=lambda t: abs(t.get("width", 0) - THUMB), default=None)
    if src.get("url") and (best is None or (best.get("width", 0) < 600 and 0 < src.get("width", 0) <= 1600)):
        return src["url"]
    return best["url"] if best else None

CATS = [  # (our id, name, freedesktop main categories in priority order)
    ("office", "Office", ["Office"]), ("graphics", "Graphics", ["Graphics"]),
    ("internet", "Internet", ["Network", "WebBrowser"]), ("media", "Music & Video", ["AudioVideo", "Audio", "Video"]),
    ("games", "Games", ["Game"]), ("dev", "Developer", ["Development"]), ("education", "Education", ["Education"]),
    ("science", "Science", ["Science"]), ("editors", "Editors", ["TextEditor"]), ("system", "System", ["System", "Settings"]),
    ("utilities", "Utilities", ["Utility"]),
]
def category(fd):
    fd = fd or []
    if "TextEditor" in fd: return "editors"
    for cid, _, keys in CATS:
        if any(k in fd for k in keys): return cid
    return "utilities"

def text(d, key):
    v = d.get(key) or {}
    return v.get("C") or v.get("en") or next(iter(v.values()), "") if isinstance(v, dict) else str(v)

def plain(htmltext, n=700):
    t = re.sub(r"<li>", "• ", htmltext or ""); t = re.sub(r"</p>|</li>", "\n", t); t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(re.sub(r"[ \t]+", " ", t)).strip()
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return (t[:n].rsplit(" ", 1)[0] + "…") if len(t) > n else t

docs = yaml.load_all(gzip.open(fetch(f"Components-{a.arch}.yml.gz"), "rt"), Loader=yaml.CSafeLoader)
header = next(docs)
if header.get("MediaBaseUrl"): MEDIA = header["MediaBaseUrl"].rstrip("/") + "/"
print(f"DEP-11 {header.get('Origin')} generated {header.get('Time')}")
comps = []
for d in docs:
    if d.get("Type") != "desktop-application": continue
    desk = (d.get("Launchable") or {}).get("desktop-id") or []
    if not desk or not d.get("Package"): continue
    if "NoDisplay" in str(d.get("Categories")): continue
    comps.append(d)
per_pkg = {}
for d in comps: per_pkg[d["Package"]] = per_pkg.get(d["Package"], 0) + 1

curated = json.load(open(os.path.join(ROOT, "curated.json")))
cur_by_id = {x["id"]: x for x in curated["apps"]}
verified = set(curated.get("verified", []))
featured = curated.get("featured", [])

apps = {}
icon_names = {}
for d in comps:
    pkg = d["Package"]; did = d["Launchable"]["desktop-id"][0]
    aid = pkg if per_pkg[pkg] == 1 else re.sub(r"[^a-z0-9_.-]", "-", did.removesuffix(".desktop").lower())
    icon = d.get("Icon") or {}
    remote = sorted(icon.get("remote") or [], key=lambda r: -r.get("width", 0))
    cached = [c for c in icon.get("cached") or [] if c.get("width") == 128]
    if cached: icon_names[aid] = cached[0]["name"]
    shots = []
    for s in d.get("Screenshots") or []:
        url = shot_url(s)
        if url: shots.append(MEDIA + url)
    apps[aid] = {
        "id": aid, "name": text(d, "Name"), "summary": text(d, "Summary"), "description": plain(text(d, "Description")),
        "category": category(d.get("Categories")), "source": "debian", "packages": [pkg],
        "command": ["hatch-desktop", did], "desktopId": did,
        "iconUrl": (MEDIA + remote[0]["url"]) if remote else "", "screenshots": shots[:4],
        "license": d.get("ProjectLicense", ""),
    }

# Curated entries override/extend generated ones (keep their tested commands & flags).
# "standalone": a curated app of its own (e.g. DOOM = crispy-doom + Freedoom) that must not absorb the generated entry
# for its first package; "screenshotsFrom": borrow another entry's DEP-11 screenshots (and category/licence if unset).
for cid, c in cur_by_id.items():
    c = dict(c); standalone = c.pop("standalone", False); src = c.pop("screenshotsFrom", None)
    if src and src in apps:
        for k in ("screenshots", "category", "license"):
            if not c.get(k) and apps[src].get(k): c[k] = apps[src][k]
    if standalone: apps[cid] = c; continue
    base = apps.get(cid) or next((x for x in apps.values() if c.get("packages") and x.get("packages") == c["packages"][:1]), None) or {}
    merged = {**base, **{k: v for k, v in c.items() if v not in (None, "", [])}}
    if base and "desktopId" in base and c.get("command"): merged["command"] = c["command"]
    if base: merged["category"] = base["category"]   # AppStream categories beat our old hand-picked ones
    if base and base["id"] != cid: apps.pop(base["id"], None)
    apps[cid] = merged

for x in apps.values():
    x["featured"] = x["id"] in featured
    x["verified"] = x["id"] in verified
order = {k: i for i, k in enumerate(featured)}
out = sorted(apps.values(), key=lambda x: (order.get(x["id"], 10_000), x["name"].lower()))

cats = [{"id": cid, "name": n} for cid, n, _ in CATS] + [{"id": "windows", "name": "Windows"}]
OUT = os.path.abspath(a.out); os.makedirs(os.path.join(OUT, "icons"), exist_ok=True)
# Icons: curated first, then DEP-11 128px for featured apps that don't have one.
have = set()
for f in os.listdir(os.path.join(ROOT, "icons")):
    if f.endswith(".png"): shutil.copy(os.path.join(ROOT, "icons", f), os.path.join(OUT, "icons", f)); have.add(f[:-4])
want = {icon_names[i]: i for i in featured if i in icon_names and i not in have}
with tarfile.open(fetch("icons-128x128.tar.gz")) as tf:
    for m in tf:
        if m.name in want:
            open(os.path.join(OUT, "icons", want[m.name] + ".png"), "wb").write(tf.extractfile(m).read()); have.add(want[m.name])
for x in out:
    if x["id"] in have: x["iconUrl"] = f"icons/{x['id']}.png"
updated = os.environ.get("CATALOGUE_UPDATED") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
cat = {"schemaVersion": 2, "version": 2, "updated": updated, "categories": cats, "apps": out}
cat["apps"] = [{k: v for k, v in a.items() if v is not None and v != "" and v != [] and v is not False or k in ("id","name","summary","command","packages","category")} for a in cat["apps"]]
s = json.dumps(cat, ensure_ascii=False, separators=(",", ":"))
open(os.path.join(OUT, "catalogue.json"), "w").write(s)
with gzip.open(os.path.join(OUT, "catalogue.json.gz"), "wb", 9) as g: g.write(s.encode())
print(f"{len(out)} apps ({sum(1 for x in out if x['featured'])} featured), {len(have)} icons, {len(s)//1024} KB, updated {updated}")
