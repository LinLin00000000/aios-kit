#!/usr/bin/env bash
# Build release archives for the Go/huh AIOS installer frontend.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
OUT_DIR="${1:-$ROOT_DIR/dist/aios-install}"
VERSION="${AIOS_INSTALL_VERSION:-$(git -C "$ROOT_DIR" describe --tags --always --dirty 2>/dev/null || echo dev)}"
TMP_DIRS=()

cleanup() {
  if ((${#TMP_DIRS[@]})); then
    rm -rf "${TMP_DIRS[@]}"
  fi
}
trap cleanup EXIT

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/aios-install_*.tar.gz "$OUT_DIR"/aios-install_checksums.txt

targets=(
  linux/amd64
  linux/arm64
  darwin/amd64
  darwin/arm64
  windows/amd64
  windows/arm64
)

build_target() {
  target="$1"
  goos="${target%/*}"
  goarch="${target#*/}"
  bin="aios-install"
  if [[ "$goos" == windows ]]; then
    bin="aios-install.exe"
  fi

  tmp="$(mktemp -d)"
  TMP_DIRS+=("$tmp")
  echo "==> building $target"
  (
    cd "$ROOT_DIR"
    CGO_ENABLED=0 GOOS="$goos" GOARCH="$goarch" \
      go build -trimpath -ldflags "-s -w -X main.version=$VERSION" -o "$tmp/$bin" ./cmd/aios-install
  )
  tar -C "$tmp" -czf "$OUT_DIR/aios-install_${goos}_${goarch}.tar.gz" "$bin"
}

for target in "${targets[@]}"; do
  build_target "$target"
done

(
  cd "$OUT_DIR"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum aios-install_*.tar.gz > aios-install_checksums.txt
  else
    shasum -a 256 aios-install_*.tar.gz > aios-install_checksums.txt
  fi
)

echo "==> release artifacts written to $OUT_DIR"
