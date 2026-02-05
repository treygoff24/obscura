#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: ./scripts/package_macos.sh

Build release artifacts for macOS:
  - dist/Obscura.app
  - release/Obscura-<version>-macos-<arch>.zip
  - release/Obscura-<version>-macos-<arch>.dmg

Optional environment variables:
  PYTHON_BIN                 Python executable (default: python3)
  APP_NAME                   App bundle name (default: Obscura)
  OBSCURA_LANGUAGES          OCR languages to bundle (default: eng+spa)
  OBSCURA_CODESIGN_IDENTITY  Developer ID identity for codesign
  OBSCURA_NOTARY_PROFILE     Keychain profile for xcrun notarytool
EOF
  exit 0
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_NAME="${APP_NAME:-Obscura}"
OBSCURA_LANGUAGES="${OBSCURA_LANGUAGES:-eng+spa}"
ENTITLEMENTS="${ROOT_DIR}/scripts/Obscura.entitlements"
DIST_APP="dist/${APP_NAME}.app"
RELEASE_DIR="release"
ARCH="$(uname -m)"

# -- Pre-flight checks -------------------------------------------------------

if ! command -v "$PYTHON_BIN" &>/dev/null; then
  echo "Error: PYTHON_BIN='${PYTHON_BIN}' not found or not executable." >&2
  echo "Set PYTHON_BIN to a valid Python 3.12+ interpreter." >&2
  exit 1
fi

for tool in hdiutil ditto codesign; do
  if ! command -v "$tool" &>/dev/null; then
    echo "Error: Required tool '${tool}' not found on PATH." >&2
    exit 1
  fi
done

if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "Error: Entitlements file not found at ${ENTITLEMENTS}" >&2
  exit 1
fi

# -- Resolve version ----------------------------------------------------------

VERSION="$("$PYTHON_BIN" - <<'PY'
import pathlib
import re

init_py = pathlib.Path("src/obscura/__init__.py").read_text(encoding="utf-8")
match = re.search(r'__version__\s*=\s*"([^"]+)"', init_py)
if not match:
    raise SystemExit("Could not determine obscura version from src/obscura/__init__.py")
print(match.group(1))
PY
)"

ARTIFACT_BASE="${APP_NAME}-${VERSION}-macos-${ARCH}"
ZIP_PATH="${RELEASE_DIR}/${ARTIFACT_BASE}.zip"
DMG_PATH="${RELEASE_DIR}/${ARTIFACT_BASE}.dmg"

echo "Building ${APP_NAME}.app ..."
"$PYTHON_BIN" build.py --languages "$OBSCURA_LANGUAGES"

if [[ ! -d "$DIST_APP" ]]; then
  echo "Build failed: ${DIST_APP} not found." >&2
  exit 1
fi

if [[ -n "${OBSCURA_CODESIGN_IDENTITY:-}" ]]; then
  echo "Codesigning app bundle ..."
  codesign \
    --force \
    --deep \
    --options runtime \
    --timestamp \
    --entitlements "$ENTITLEMENTS" \
    --sign "$OBSCURA_CODESIGN_IDENTITY" \
    "$DIST_APP"
  codesign --verify --deep --strict --verbose=2 "$DIST_APP"
else
  echo "Skipping codesign (set OBSCURA_CODESIGN_IDENTITY to enable)."
fi

rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

echo "Creating zip artifact ..."
ditto -c -k --keepParent "$DIST_APP" "$ZIP_PATH"

echo "Creating dmg artifact ..."
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$DIST_APP" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

if [[ -n "${OBSCURA_NOTARY_PROFILE:-}" ]]; then
  echo "Submitting dmg for notarization ..."
  xcrun notarytool submit "$DMG_PATH" --keychain-profile "$OBSCURA_NOTARY_PROFILE" --wait
  echo "Stapling notarization ticket ..."
  xcrun stapler staple "$DMG_PATH"
else
  echo "Skipping notarization (set OBSCURA_NOTARY_PROFILE to enable)."
fi

if [[ -n "${OBSCURA_CODESIGN_IDENTITY:-}" ]]; then
  echo "Running Gatekeeper assessment ..."
  spctl -a -t open --context context:primary-signature -v "$DIST_APP"
fi

echo "Done."
echo "Artifacts:"
echo "  - ${ZIP_PATH}"
echo "  - ${DMG_PATH}"
