#!/usr/bin/env bash
# Fetch the pinned whisper.cpp CLI binary and place it as a Tauri sidecar
# (apps/desktop/src-tauri/binaries/whisper-cli-<target-triple>).
# Runs per-platform locally and in CI so the binary never lives in git.
set -euo pipefail

WHISPER_VERSION="${WHISPER_VERSION:-1.9.1}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="$ROOT/apps/desktop/src-tauri/binaries"
mkdir -p "$OUT_DIR"

# Resolve the Rust target triple (arg 1 overrides; else host).
TRIPLE="${1:-$(rustc -Vv | sed -n 's/host: //p')}"

# whisper.cpp release asset naming mirrors the project's CI matrix.
# Pre-built binaries are published per-platform; we map the Rust triple
# to the asset name and strip any archive wrapper.
case "$TRIPLE" in
  aarch64-apple-darwin)
    # macOS ARM64: download the xcframework and extract the CLI binary.
    ASSET="whisper-cli"
    ARCHIVE="whisper-v${WHISPER_VERSION}-xcframework.zip" ;;
  x86_64-apple-darwin)
    # No pre-built macOS x64 binary — build from source.
    echo "No pre-built macOS x64 binary. Build from source:" >&2
    echo "  git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp && cmake -B build && cmake --build build --config Release" >&2
    echo "Then copy build/bin/Release/whisper-cli to $OUT_DIR/whisper-cli-$TRIPLE" >&2
    exit 1 ;;
  x86_64-pc-windows-msvc)
    ASSET="whisper-cli.exe"
    ARCHIVE="whisper-bin-x64.zip" ;;
  aarch64-pc-windows-msvc)
    ASSET="whisper-cli.exe"
    ARCHIVE="whisper-bin-Win32.zip" ;;  # Win32 zip also contains ARM64 builds in newer releases
  x86_64-unknown-linux-gnu)
    ASSET="whisper-cli"
    ARCHIVE="whisper-bin-ubuntu-x64.tar.gz" ;;
  aarch64-unknown-linux-gnu)
    ASSET="whisper-cli"
    ARCHIVE="whisper-bin-ubuntu-arm64.tar.gz" ;;
  *)
    echo "Unsupported triple: $TRIPLE" >&2
    echo "Build whisper.cpp from source: https://github.com/ggml-org/whisper.cpp" >&2
    exit 1
    ;;
esac

URL="https://github.com/ggml-org/whisper.cpp/releases/download/v${WHISPER_VERSION}/${ARCHIVE}"
TMP="$(mktemp -d)"
echo "Downloading $URL"
curl -fsSL "$URL" -o "$TMP/$ARCHIVE"

case "$ARCHIVE" in
  *.tar.gz)
    tar -xzf "$TMP/$ARCHIVE" -C "$TMP"
    ;;
  *.zip)
    if command -v unzip >/dev/null 2>&1; then
      unzip -oq "$TMP/$ARCHIVE" -d "$TMP"
    else
      tar -xf "$TMP/$ARCHIVE" -C "$TMP"   # bsdtar (macOS/Windows) extracts zip
    fi
    ;;
esac

# The archive may contain a flat binary or a nested directory — find it.
# The Windows zip has a Release/ subdirectory; the macOS xcframework has
# a different layout.
BIN="$(find "$TMP" -type f -name "$ASSET" | head -1)"
if [ -z "$BIN" ]; then
  # Some releases use different naming — try without extension.
  BIN="$(find "$TMP" -type f -name "whisper-cli*" -not -name "*.dll" -not -name "*.lib" | head -1)"
fi
if [ -z "$BIN" ]; then
  echo "Could not find $ASSET inside the archive" >&2
  ls -la "$TMP"
  exit 1
fi

if [[ "$ASSET" == *.exe ]]; then
  cp "$BIN" "$OUT_DIR/whisper-cli-$TRIPLE.exe"
else
  cp "$BIN" "$OUT_DIR/whisper-cli-$TRIPLE"
  chmod +x "$OUT_DIR/whisper-cli-$TRIPLE"
fi

rm -rf "$TMP"
echo "Placed whisper-cli sidecar for $TRIPLE in $OUT_DIR"
