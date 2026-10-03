#!/bin/sh
set -eu
task_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
helper_bundle="$task_root/.runtime/MiwlVoice.app"
mkdir -p "$helper_bundle/Contents/MacOS"
cp "$task_root/native/Info.plist" "$helper_bundle/Contents/Info.plist"
/Library/Developer/CommandLineTools/usr/bin/swiftc -O -target arm64-apple-macosx14.0 \
  -sdk "$(/usr/bin/xcrun --show-sdk-path)" \
  "$task_root/native/MiwlVoice.swift" -o "$helper_bundle/Contents/MacOS/MiwlVoice"
/usr/bin/codesign --force --sign - --options runtime \
  --entitlements "$task_root/native/entitlements.plist" "$helper_bundle"
/usr/bin/codesign --verify --deep --strict "$helper_bundle"
