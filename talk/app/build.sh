#!/bin/bash
# talk/app/build.sh — compile Stub.swift and sign it into <out>/<name>.app
#   build.sh [--identity NAME] [--bundle-id ID] [--name NAME] [--out DIR]
# Builds only; install.sh moves the result into ~/Applications with a backup.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
# shellcheck source=lib/identity.sh
source "$ROOT/lib/identity.sh"
NAME="talk-speak"; BUNDLE_ID="com.studentofai.talk-speak"; OUT="$ROOT/build"
while [ $# -gt 0 ]; do
  case "$1" in
    --identity)  IDENTITY="$2"; shift 2;;
    --bundle-id) BUNDLE_ID="$2"; shift 2;;
    --name)      NAME="$2"; shift 2;;
    --out)       OUT="$2"; shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
APP="$OUT/$NAME.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
swiftc -O "$HERE/Stub.swift" -o "$APP/Contents/MacOS/$NAME"
sed -e "s#__BUNDLE_ID__#$BUNDLE_ID#g" -e "s#__NAME__#$NAME#g" -e "s#__VERSION__#$VERSION#g" \
    "$HERE/Info.plist.tmpl" > "$APP/Contents/Info.plist"
identity_create || { echo "FAIL: could not create signing identity '$IDENTITY'" >&2; exit 1; }
codesign --force --sign "$IDENTITY" --identifier "$BUNDLE_ID" "$APP"
codesign --verify --verbose=2 "$APP"
echo "built: $APP ($VERSION)"
codesign -d -r- "$APP" 2>&1 | /usr/bin/grep designated
