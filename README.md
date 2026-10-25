# hatch-catalogue

The Hatch store's app list, maintained here so that adding or fixing an app never needs an app update.

- `curated.json`: hand-curated entries (vendor repos, Flathub, GitHub releases, Windows apps, featured/verified lists). Everything else is generated from Debian 13's AppStream (DEP-11) by `scripts/build.py`.
- `icons/<id>.png`: icons for curated entries (32–512 px PNG, ≤ 512 KB).
- **PRs:** `PR checks` validates the schema, builds the full catalogue, then installs and launches every new or changed entry in a real Debian 13 arm64 guest (Hatch's own scripts and compositor) and uploads screenshots.
- **Merge to main / nightly:** `Publish catalogue` builds, validates, Ed25519-signs (`catalogue.json.sig`, over the uncompressed JSON) and publishes `catalogue.json(.gz)` + icons as the `latest` release.
- **App side:** fetches `releases/latest/download/catalogue.json.gz` on launch and every 12 h (ETag), verifies with the public key in `signing-public-key.b64` (baked into the app), caches it, and falls back to its bundled copy. Unknown entry types are skipped; a newer `schemaVersion` is ignored.

The private signing key is the `CATALOGUE_SIGNING_KEY` Actions secret, available only to the publish workflow (push to main, nightly, manual). PR checks run with read-only permissions and no secrets, so fork PRs never see the key. The app fetches `releases/latest/download/catalogue.json.gz` anonymously (URL configurable via the `catalogueUrl` Gradle property or the in-app developer setting).
