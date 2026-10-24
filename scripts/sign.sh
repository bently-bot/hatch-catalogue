#!/usr/bin/env bash
# Ed25519-sign the *uncompressed* catalogue: dist/catalogue.json → dist/catalogue.json.sig (base64, one line).
# Key: $CATALOGUE_SIGNING_KEY (PEM, from the Actions secret) or a PEM file path in $CATALOGUE_SIGNING_KEY_FILE.
# Never echo the key. Verifies with the public key afterwards when CATALOGUE_PUBKEY (base64 raw 32 bytes) is set.
set -euo pipefail
D="${1:-dist}"; K=$(mktemp); trap 'rm -f "$K" "$K.sig" "$K.pub"' EXIT; chmod 600 "$K"
if [ -n "${CATALOGUE_SIGNING_KEY_FILE:-}" ]; then cp "$CATALOGUE_SIGNING_KEY_FILE" "$K"; else printf '%s\n' "${CATALOGUE_SIGNING_KEY:?missing}" > "$K"; fi
openssl pkeyutl -sign -rawin -inkey "$K" -in "$D/catalogue.json" -out "$K.sig"
base64 -w0 "$K.sig" > "$D/catalogue.json.sig"; echo >> "$D/catalogue.json.sig"
if [ -n "${CATALOGUE_PUBKEY:-}" ]; then
  { printf '\x30\x2a\x30\x05\x06\x03\x2b\x65\x70\x03\x21\x00'; echo "$CATALOGUE_PUBKEY" | base64 -d; } > "$K.pub.der"
  openssl pkey -pubin -inform DER -in "$K.pub.der" -out "$K.pub" && rm -f "$K.pub.der"
  openssl pkeyutl -verify -rawin -pubin -inkey "$K.pub" -in "$D/catalogue.json" -sigfile "$K.sig" >/dev/null
  echo "signature verified against the app's public key"
fi
