#!/usr/bin/env bash
# Fetch the bundled scientific skills pack into runtime/skills/external/.
# The pack is hosted on the project's own repository; set GIT_URL + COMMIT to
# the pack's release you want to pin.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="$ROOT/runtime/skills/external/jingming-skills"
GIT_URL="${JINGMING_SKILLS_URL:-https://github.com/hzf716666/jingming-yanhuan-skills}"
COMMIT="${JINGMING_SKILLS_COMMIT:-main}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Fetching skills pack from $GIT_URL @ $COMMIT ..."
git clone --depth 1 --branch "$COMMIT" "$GIT_URL" "$TMP/pack"
mkdir -p "$(dirname "$OUT_DIR")"
rm -rf "$OUT_DIR"
mv "$TMP/pack" "$OUT_DIR"
echo "Placed skills pack in $OUT_DIR"
