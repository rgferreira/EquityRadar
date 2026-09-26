#!/bin/zsh

set -euo pipefail

PROJECT_ROOT="/Users/rafaelgonzalezferreira/Documents/PersonalEquityRadar"
SOURCE_DIR="$PROJECT_ROOT/scripts/macos"
DEFAULT_DESTINATION="/Users/rafaelgonzalezferreira/Applications/Equity Radar.app"
DESKTOP_LINK="/Users/rafaelgonzalezferreira/Desktop/Equity Radar.app"
LAUNCH_SERVICES_REGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
DESTINATION="${1:-$DEFAULT_DESTINATION}"
BUILD_ROOT="$(/usr/bin/mktemp -d /private/tmp/equity-radar-launcher.XXXXXX)"
DERIVED_DATA="$BUILD_ROOT/DerivedData"
APP_BUNDLE="$DERIVED_DATA/Build/Products/Release/Equity Radar.app"
PREVIOUS_APP="$BUILD_ROOT/Previous Equity Radar.app"
PATCHED_APP="$BUILD_ROOT/Equity Radar.app"
PREVIOUS_DESKTOP_APP="$BUILD_ROOT/Previous Desktop Equity Radar.app"

cleanup() {
  /bin/rm -rf "$BUILD_ROOT"
}
trap cleanup EXIT

if [[ -d /Applications/Xcode.app/Contents/Developer ]]; then
  DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer" \
    /usr/bin/xcodebuild \
    -project "$SOURCE_DIR/EquityRadarLauncher.xcodeproj" \
    -scheme EquityRadarLauncher \
    -configuration Release \
    -derivedDataPath "$DERIVED_DATA" \
    build >/dev/null
  /usr/bin/codesign --verify --deep --strict "$APP_BUNDLE"
else
  EXISTING_APP="$DESTINATION"
  if [[ ! -d "$EXISTING_APP" && -d "$DESKTOP_LINK" ]]; then
    EXISTING_APP="$DESKTOP_LINK"
  fi
  if [[ ! -d "$EXISTING_APP" ]]; then
    print -u2 -r -- "Full Xcode is unavailable and no existing launcher can be safely refreshed."
    exit 2
  fi
  # Command Line Tools can rebuild the SwiftUI launcher even when the full
  # Xcode app is unavailable. Preserve the existing widget bundle, replace the
  # main executable and controller in a temporary copy, then re-sign it.
  /usr/bin/ditto "$EXISTING_APP" "$PATCHED_APP"
  /usr/bin/swiftc -O -parse-as-library \
    -target arm64-apple-macosx26.0 \
    "$SOURCE_DIR/EquityRadarLauncher.swift" \
    "$SOURCE_DIR/EquityRadarWidgetSupport.swift" \
    -o "$PATCHED_APP/Contents/MacOS/EquityRadar" \
    -framework SwiftUI -framework WidgetKit
  /bin/cp "$SOURCE_DIR/equity-radar-control.zsh" \
    "$PATCHED_APP/Contents/Resources/equity-radar-control.zsh"
  /bin/chmod 755 "$PATCHED_APP/Contents/Resources/equity-radar-control.zsh"
  /bin/cp "$SOURCE_DIR/Resources/EquityRadar.icns" \
    "$PATCHED_APP/Contents/Resources/EquityRadar.icns"
  # Keep privacy declarations in sync when Command Line Tools patches an
  # existing bundle instead of asking Xcode to rebuild it from Info.plist.
  /bin/cp "$SOURCE_DIR/Info.plist" "$PATCHED_APP/Contents/Info.plist"
  /usr/bin/xattr -cr "$PATCHED_APP"
  # Command Line Tools has no Xcode-managed provisioning profile for the App
  # Group entitlement. A local ad-hoc signature is valid for this personal app
  # and avoids an Apple Development signature that amfid rejects as unprovisioned.
  /usr/bin/codesign --force --sign - "$PATCHED_APP"
  /usr/bin/codesign --verify --deep --strict "$PATCHED_APP"
  APP_BUNDLE="$PATCHED_APP"
  print -r -- "Full Xcode unavailable; rebuilt and locally signed the native launcher."
fi

/bin/mkdir -p "${DESTINATION:h}"
if [[ -e "$DESTINATION" || -L "$DESTINATION" ]]; then
  /bin/mv "$DESTINATION" "$PREVIOUS_APP"
fi
if ! /usr/bin/ditto "$APP_BUNDLE" "$DESTINATION"; then
  if [[ -e "$PREVIOUS_APP" ]]; then
    /bin/mv "$PREVIOUS_APP" "$DESTINATION"
  fi
  print -u2 -r -- "Launcher installation failed; the previous app was restored."
  exit 1
fi
# Remove only extended metadata from the freshly installed local bundle before
# strict checking. The canonical bundle never lives in File Provider-managed Desktop.
/usr/bin/xattr -cr "$DESTINATION"
if ! /usr/bin/codesign --verify --deep --strict "$DESTINATION"; then
  /bin/mv "$DESTINATION" "$BUILD_ROOT/Invalid Equity Radar.app"
  if [[ -e "$PREVIOUS_APP" ]]; then
    /bin/mv "$PREVIOUS_APP" "$DESTINATION"
  fi
  print -u2 -r -- "Installed launcher verification failed; the previous app was restored."
  exit 4
fi
/usr/bin/touch "$DESTINATION"
if [[ -x "$LAUNCH_SERVICES_REGISTER" ]]; then
  "$LAUNCH_SERVICES_REGISTER" -f "$DESTINATION" >/dev/null 2>&1 || true
fi
if [[ "$DESTINATION" == "$DEFAULT_DESTINATION" ]]; then
  if [[ -e "$DESKTOP_LINK" || -L "$DESKTOP_LINK" ]]; then
    /bin/mv "$DESKTOP_LINK" "$PREVIOUS_DESKTOP_APP"
  fi
  if ! /bin/ln -s "$DESTINATION" "$DESKTOP_LINK"; then
    if [[ -e "$PREVIOUS_DESKTOP_APP" || -L "$PREVIOUS_DESKTOP_APP" ]]; then
      /bin/mv "$PREVIOUS_DESKTOP_APP" "$DESKTOP_LINK"
    fi
    print -u2 -r -- "Desktop launcher link failed; the previous Desktop item was restored."
    exit 5
  fi
  print -r -- "Desktop launcher link points to the local canonical app."
fi
print -r -- "Native launcher installed at $DESTINATION"
