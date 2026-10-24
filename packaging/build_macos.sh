#!/usr/bin/env bash
# Build ReserveMe for macOS: creates dist/ReserveMe.app and dist/ReserveMe-<version>-<arch>.dmg
# Needs: Python 3.12 from python.org or Homebrew, Xcode command line tools.
#
# Optional signing + notarization (needed so other Macs open it without warnings):
#   export MAC_SIGN_ID="Developer ID Application: Your Name (TEAMID)"
#   export MAC_NOTARY_PROFILE="reserveme-notary"   # created once with: xcrun notarytool store-credentials
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3.12}
command -v "$PY" >/dev/null || PY=python3
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

python -m pytest -q tests
pyinstaller packaging/reserveme.spec --noconfirm --clean

VERSION=$(python -c "import reserveme; print(reserveme.__version__)")
ARCH=$(uname -m)
APP=dist/ReserveMe.app

if [[ -n "${MAC_SIGN_ID:-}" ]]; then
  echo "Signing with $MAC_SIGN_ID"
  codesign --force --deep --options runtime --timestamp \
    --entitlements packaging/entitlements.plist --sign "$MAC_SIGN_ID" "$APP"
  codesign --verify --deep --strict --verbose=2 "$APP"
fi

DMG="dist/ReserveMe-${VERSION}-${ARCH}.dmg"
rm -f "$DMG"
STAGE=$(mktemp -d)
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "ReserveMe" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

if [[ -n "${MAC_SIGN_ID:-}" ]]; then
  codesign --force --timestamp --sign "$MAC_SIGN_ID" "$DMG"
  if [[ -n "${MAC_NOTARY_PROFILE:-}" ]]; then
    xcrun notarytool submit "$DMG" --keychain-profile "$MAC_NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG"
  fi
fi
echo "Done: $DMG"
