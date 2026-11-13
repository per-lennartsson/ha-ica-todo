#!/bin/sh
# Packages the integration as dist/ica.zip for a release (HACS zip_release).
#
#   scripts/package-release.sh v0.12.0
#
# The zip holds the contents of custom_components/ica/ with the tag's version
# stamped into manifest.json. HACS unpacks it into custom_components/ica/.
set -eu

TAG="${1:?usage: package-release.sh vMAJOR.MINOR.PATCH}"
case "$TAG" in
  v[0-9]*.[0-9]*.[0-9]*) ;;
  *) echo "The tag must look like v1.2.3, got: $TAG" >&2; exit 1 ;;
esac
VERSION="${TAG#v}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/custom_components/ica"
OUT="$ROOT/dist"

rm -rf "$OUT"
mkdir -p "$OUT/ica"
cp -R "$SRC/." "$OUT/ica/"
find "$OUT/ica" -name __pycache__ -type d -prune -exec rm -rf {} +
rm -f "$OUT/ica/.gitignore"

python3 - "$OUT/ica/manifest.json" "$VERSION" <<'PY'
import json
import sys

path, version = sys.argv[1:3]
with open(path, encoding="utf-8") as file:
    manifest = json.load(file)
manifest["version"] = version
with open(path, "w", encoding="utf-8") as file:
    json.dump(manifest, file, indent=2, ensure_ascii=False)
    file.write("\n")
PY

(cd "$OUT/ica" && zip -qr -X ../ica.zip .)
echo "Built $OUT/ica.zip for $TAG"
