#!/usr/bin/env python3
"""Schema check for curated.json (+ optionally a built dist/catalogue.json). Exit 1 with readable errors.
Rules mirror what the app can install: hatch/app/src/main/kotlin/dev/hatch/store/Catalogue.kt + CatalogueCodec.kt."""
import json, os, re, struct, sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
SOURCES = {"debian", "vendor", "flathub", "release", "winget", "wine"}
ID = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,99}$", re.I)
errs = []
def err(i, m): errs.append(f"{i}: {m}")

def check_app(a, where):
    i = a.get("id", "?")
    if not ID.match(str(a.get("id", ""))): err(i, f"{where}: bad or missing id")
    for k in ("name", "source"):
        if not isinstance(a.get(k), str) or not a[k].strip(): err(i, f"{where}: missing {k}")
    src = a.get("source")
    if src not in SOURCES: err(i, f"{where}: unknown source {src!r} (known: {sorted(SOURCES)})")
    cmd = a.get("command")
    if cmd is not None and (not isinstance(cmd, list) or not all(isinstance(c, str) and c for c in cmd)): err(i, f"{where}: command must be a list of strings")
    if src == "vendor":
        r = a.get("repo") or {}
        for k in ("id", "keyUrl", "uris", "suites"):
            if not r.get(k): err(i, f"vendor entry needs repo.{k}")
        if r.get("keyUrl") and not r["keyUrl"].startswith("https://"): err(i, "repo.keyUrl must be https")
        if not a.get("packages"): err(i, "vendor entry needs packages")
    if src == "flathub":
        if not re.match(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+){2,}$", a.get("flatpak", "")): err(i, "flathub entry needs a reverse-DNS flatpak id")
    if src in ("release", "winget", "wine"):
        pays = dict(a.get("payloads") or {})
        if a.get("windowsPayload"): pays["arm64"] = a["windowsPayload"]
        if not pays: err(i, f"{src} entry needs payloads/windowsPayload")
        for arch, p in pays.items():
            if not str(p.get("url", "")).startswith("https://"): err(i, f"payload {arch}: url must be https")
            if not re.match(r"^[0-9a-f]{64}$", p.get("sha256", "")): err(i, f"payload {arch}: sha256 required (64 hex)")
            if not p.get("extractTo"): err(i, f"payload {arch}: extractTo required")
    if src == "debian" and not a.get("packages") and where == "curated": err(i, "debian entry needs packages")

def png_ok(path):
    b = open(path, "rb").read(32)
    if b[:8] != b"\x89PNG\r\n\x1a\n": return "not a PNG"
    w, h = struct.unpack(">II", b[16:24])
    if not (32 <= w <= 512 and 32 <= h <= 512): return f"size {w}x{h} (want 32..512)"
    if os.path.getsize(path) > 512 * 1024: return "larger than 512 KB"
    return None

cur = json.load(open(os.path.join(ROOT, "curated.json")))
ids = [a.get("id") for a in cur["apps"]]
for d in {x for x in ids if ids.count(x) > 1}: err(d, "duplicate id in curated.json")
for a in cur["apps"]: check_app(a, "curated")
for f in ("featured", "verified"):
    for x in cur.get(f, []):
        if not isinstance(x, str): err(x, f"{f} entries must be ids")
icons = os.path.join(ROOT, "icons")
for f in sorted(os.listdir(icons)):
    if not f.endswith(".png"): err(f, "icons/ holds only <id>.png"); continue
    p = png_ok(os.path.join(icons, f))
    if p: err(f, p)
for a in cur["apps"]:
    if a.get("source") != "debian" and not os.path.exists(os.path.join(icons, a["id"] + ".png")): err(a["id"], "non-Debian entries need icons/<id>.png")

if len(sys.argv) > 1:   # built catalogue
    c = json.load(open(sys.argv[1]))
    if c.get("schemaVersion") != 2: err("catalogue", "schemaVersion must be 2")
    if not re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", c.get("updated", "")): err("catalogue", "updated must be UTC ISO-8601")
    if len(c.get("apps", [])) < 100: err("catalogue", f"only {len(c.get('apps', []))} apps; refusing to publish a truncated catalogue")
    seen = set()
    for a in c["apps"]:
        if a["id"] in seen: err(a["id"], "duplicate id in built catalogue")
        seen.add(a["id"]); check_app(a, "built")

if errs:
    print("\n".join("ERROR " + e for e in errs)); sys.exit(1)
print(f"OK: {len(cur['apps'])} curated entries, {len(os.listdir(icons))} icons" + (f", built catalogue {sys.argv[1]} valid" if len(sys.argv) > 1 else ""))
