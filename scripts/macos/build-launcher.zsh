#!/bin/zsh

set -euo pipefail

PROJECT_ROOT="/Users/rafaelgonzalezferreira/Documents/PersonalEquityRadar"
SOURCE_DIR="$PROJECT_ROOT/scripts/macos"
DESTINATION="${1:-$HOME/Desktop/Equity Radar Launcher.app}"
BUILD_ROOT="$(/usr/bin/mktemp -d /private/tmp/equity-radar-launcher.XXXXXX)"
APP_BUNDLE="$BUILD_ROOT/Equity Radar Launcher.app"
PREVIOUS_APP="$BUILD_ROOT/Previous Equity Radar Launcher.app"

cleanup() {
  /bin/rm -rf "$BUILD_ROOT"
}
trap cleanup EXIT

/bin/mkdir -p "$APP_BUNDLE/Contents/MacOS"
/usr/bin/xcrun swiftc \
  -parse-as-library \
  -target arm64-apple-macosx13.0 \
  "$SOURCE_DIR/EquityRadarLauncher.swift" \
  -framework SwiftUI -framework AppKit \
  -o "$APP_BUNDLE/Contents/MacOS/EquityRadarLauncher"
/bin/cp "$SOURCE_DIR/Info.plist" "$APP_BUNDLE/Contents/Info.plist"
/usr/bin/codesign --force --deep --sign - "$APP_BUNDLE" >/dev/null

if [[ -e "$DESTINATION" ]]; then
  /bin/mv "$DESTINATION" "$PREVIOUS_APP"
fi
if ! /bin/mv "$APP_BUNDLE" "$DESTINATION"; then
  if [[ -e "$PREVIOUS_APP" ]]; then
    /bin/mv "$PREVIOUS_APP" "$DESTINATION"
  fi
  print -u2 -r -- "Launcher installation failed; the previous app was restored."
  exit 1
fi
print -r -- "Native launcher installed at $DESTINATION"
